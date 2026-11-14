//! Registration, proposal escrow, settlement, and refunds.

use crate::Contract;
use crate::ContractExt;
use crate::events::{
    AgentRegisteredData, MarketEvent, ProposalAcceptedData, ProposalPostedData,
    ProposalRejectedData, TradeSettledData,
};
use crate::types::{
    ACCOUNT_CREATION_YOCTO, AGENT_REGISTRATION_BYTES, AgentProfile, MAX_AMENITIES,
    MAX_ITEMS_PER_PROPOSAL, MAX_MENU, MAX_PROPOSALS_PER_CUSTOMER, OrderItem, Proposal,
    ProposalStatus, Role, TradeReceipt, cents_delta_ok, escrow_yocto, order_total,
};
use near_sdk::json_types::{I128, U64, U128};
use near_sdk::{AccountId, Allowance, NearToken, Promise, PublicKey, env, near, require};

const BUSINESS_METHODS: &str = "post_proposal,settle";

/// Account-id segments are lowercase alphanumeric with `-`/`_` separators.
fn valid_agent_name(agent_name: &str) -> bool {
    let bytes = agent_name.as_bytes();
    if bytes.is_empty() || bytes.len() > 40 {
        return false;
    }
    if !bytes.iter().all(|byte| {
        byte.is_ascii_lowercase() || byte.is_ascii_digit() || *byte == b'-' || *byte == b'_'
    }) {
        return false;
    }
    let first = bytes[0];
    let last = bytes[bytes.len() - 1];
    first != b'-' && first != b'_' && last != b'-' && last != b'_'
}

fn is_superset(proposal_items: &[OrderItem], customer_menu: &[(String, U128)]) -> bool {
    customer_menu.iter().all(|(customer_item, _)| {
        proposal_items
            .iter()
            .any(|item| item.quantity > 0 && &item.item_name == customer_item)
    })
}

fn amenities_cover(required: &[String], offered: &[String]) -> bool {
    required.iter().all(|amenity| offered.contains(amenity))
}

#[near]
impl Contract {
    /// Orchestrator registers an agent: derives `"{agent_name}.{contract}"`,
    /// creates that sub-account, installs a scoped key, and stores the profile.
    ///
    /// The attached deposit covers a fixed storage quote plus the NEP-642
    /// account-creation transfer; the remainder stays as the business proposal
    /// reserve.
    #[payable]
    pub fn register_agent(
        &mut self,
        agent_name: String,
        profile: AgentProfile,
        public_key: PublicKey,
    ) -> Promise {
        require!(
            valid_agent_name(&agent_name),
            "agent_name must be 1-40 lowercase alphanumeric/-/_ characters"
        );
        let agent_id: AccountId = format!("{agent_name}.{}", env::current_account_id())
            .parse()
            .unwrap_or_else(|_| env::panic_str("derived agent account id is invalid"));
        require!(
            !self.agents.contains_key(&agent_id),
            "agent is already registered"
        );
        require!(
            profile.menu.len() <= MAX_MENU,
            "profile menu exceeds MAX_MENU"
        );
        require!(
            profile.amenities.len() <= MAX_AMENITIES,
            "profile amenities exceeds MAX_AMENITIES"
        );
        if profile.role == Role::Business {
            require!(
                profile.payout_account != agent_id,
                "business payout_account must be a FullAccess account, not the scoped sub-account"
            );
        }

        let storage_cost = env::storage_byte_cost()
            .checked_mul(AGENT_REGISTRATION_BYTES)
            .unwrap_or_else(|| env::panic_str("storage quote overflow"));
        let required = storage_cost
            .as_yoctonear()
            .checked_add(ACCOUNT_CREATION_YOCTO)
            .unwrap_or_else(|| env::panic_str("registration quote overflow"));
        if env::attached_deposit().as_yoctonear() < required {
            env::panic_str(&format!(
                "insufficient deposit: require at least {required} yoctoNEAR"
            ));
        }

        let role = profile.role;
        self.agents.insert(agent_id.clone(), profile);
        if role == Role::Customer {
            self.welfare.registered_customers = self.welfare.registered_customers.saturating_add(1);
        }

        MarketEvent::AgentRegistered(vec![AgentRegisteredData {
            agent_id: agent_id.clone(),
            role,
        }])
        .emit();

        let promise = Promise::new(agent_id)
            .create_account()
            .transfer(NearToken::from_yoctonear(ACCOUNT_CREATION_YOCTO));
        match role {
            Role::Business => promise.add_access_key_allowance(
                public_key,
                Allowance::Unlimited,
                env::current_account_id(),
                BUSINESS_METHODS.to_string(),
            ),
            Role::Customer => promise.add_full_access_key(public_key),
        }
    }

    /// Business posts a price commitment. Validation failures are soft rejects:
    /// nothing is stored, the rejection counter advances, and a
    /// `proposal_rejected` event records the reason.
    pub fn post_proposal(
        &mut self,
        proposal_id: String,
        customer: AccountId,
        items: Vec<OrderItem>,
        total_price: U128,
        expiry: U64,
    ) {
        let business = env::predecessor_account_id();
        if let Err(reason) = self.validate_proposal(
            &business,
            &customer,
            &proposal_id,
            &items,
            total_price,
            expiry.0,
        ) {
            self.welfare.rejected_proposals = self.welfare.rejected_proposals.saturating_add(1);
            MarketEvent::ProposalRejected(vec![ProposalRejectedData {
                proposal_id,
                business,
                customer,
                reason,
            }])
            .emit();
            return;
        }

        let proposal = Proposal {
            business: business.clone(),
            customer: customer.clone(),
            items,
            total_price,
            expiry,
            status: ProposalStatus::Posted,
        };
        self.proposals.insert(proposal_id.clone(), proposal);

        let posted_count = self
            .proposal_count_by_customer
            .get(&customer)
            .copied()
            .unwrap_or(0);
        self.proposal_count_by_customer
            .insert(customer.clone(), posted_count.saturating_add(1));

        MarketEvent::ProposalPosted(vec![ProposalPostedData {
            proposal_id,
            business,
            customer,
            total_price_cents: total_price,
        }])
        .emit();
    }

    /// Customer accepts a posted proposal and escrows exactly
    /// `total_price * YOCTO_PER_USD_CENT` yoctoNEAR.
    #[payable]
    pub fn accept_proposal(&mut self, proposal_id: String) {
        let customer = env::predecessor_account_id();
        let mut proposal = self
            .proposals
            .get(&proposal_id)
            .cloned()
            .unwrap_or_else(|| env::panic_str("proposal not found"));
        require!(
            proposal.status == ProposalStatus::Posted,
            "proposal is not posted"
        );
        require!(
            proposal.customer == customer,
            "only the proposal customer may accept"
        );
        let expected = escrow_yocto(proposal.total_price.0)
            .unwrap_or_else(|| env::panic_str("escrow amount overflow"));
        require!(
            env::attached_deposit().as_yoctonear() == expected,
            "attached deposit must equal total_price * YOCTO_PER_USD_CENT"
        );
        require!(
            env::block_timestamp() < proposal.expiry.0,
            "proposal has expired"
        );

        proposal.status = ProposalStatus::Funded;
        self.proposals.insert(proposal_id.clone(), proposal);
        MarketEvent::ProposalAccepted(vec![ProposalAcceptedData {
            proposal_id,
            customer,
            amount_yocto: U128(expected),
        }])
        .emit();
    }

    /// Business confirms delivery and pulls escrow minus the fee. State is
    /// marked settled before the transfer; the status guard prevents replay.
    pub fn settle(&mut self, proposal_id: String) -> Promise {
        let business = env::predecessor_account_id();
        let mut proposal = self
            .proposals
            .get(&proposal_id)
            .cloned()
            .unwrap_or_else(|| env::panic_str("proposal not found"));
        require!(
            proposal.status == ProposalStatus::Funded,
            "proposal is not funded"
        );
        require!(
            proposal.business == business,
            "only the proposal business may settle"
        );

        let customer_profile = self
            .agents
            .get(&proposal.customer)
            .cloned()
            .unwrap_or_else(|| env::panic_str("customer profile not found"));
        let business_profile = self
            .agents
            .get(&proposal.business)
            .cloned()
            .unwrap_or_else(|| env::panic_str("business profile not found"));

        let price = proposal.total_price.0;
        let fee = price
            .checked_mul(u128::from(self.fee_bps))
            .unwrap_or_else(|| env::panic_str("fee overflow"))
            / 10_000;
        let revenue = price.saturating_sub(fee);
        let needs_met = is_superset(&proposal.items, &customer_profile.menu)
            && amenities_cover(&customer_profile.amenities, &business_profile.amenities);

        proposal.status = ProposalStatus::Settled;
        self.proposals.insert(proposal_id.clone(), proposal.clone());

        let first = if needs_met {
            self.customers_needs_met.insert(proposal.customer.clone())
        } else {
            false
        };
        if first {
            self.welfare.needs_met_count = self.welfare.needs_met_count.saturating_add(1);
        }
        let match_score = customer_profile.requested_total_cents.0.saturating_mul(2);
        let match_score_signed = i128::try_from(match_score).unwrap_or(i128::MAX);
        let price_signed = i128::try_from(price).unwrap_or(i128::MAX);
        let delta = if first {
            match_score_signed.saturating_sub(price_signed)
        } else {
            0i128.saturating_sub(price_signed)
        };
        let utility_delta = I128(delta);
        self.welfare.total_customer_utility_cents = I128(
            self.welfare
                .total_customer_utility_cents
                .0
                .saturating_add(delta),
        );

        self.welfare.total_business_revenue_cents = U128(
            self.welfare
                .total_business_revenue_cents
                .0
                .saturating_add(revenue),
        );

        let paid_before = self
            .paid_cents_by_customer
            .get(&proposal.customer)
            .copied()
            .unwrap_or(U128(0))
            .0;
        if paid_before == 0 {
            self.welfare.purchasing_customers = self.welfare.purchasing_customers.saturating_add(1);
        }
        self.paid_cents_by_customer.insert(
            proposal.customer.clone(),
            U128(paid_before.saturating_add(price)),
        );

        self.welfare.settled_count = self.welfare.settled_count.saturating_add(1);
        let receipt = TradeReceipt {
            proposal_id: proposal_id.clone(),
            customer: proposal.customer.clone(),
            business: proposal.business.clone(),
            price: U128(price),
            fee: U128(fee),
            needs_met,
            ts: U64(env::block_timestamp()),
        };
        self.trade_log.push(receipt);

        MarketEvent::TradeSettled(vec![TradeSettledData {
            proposal_id: proposal_id.clone(),
            customer: proposal.customer.clone(),
            business: proposal.business.clone(),
            price_cents: U128(price),
            fee_cents: U128(fee),
            needs_met,
            customer_utility_delta_cents: utility_delta,
            business_revenue_delta_cents: U128(revenue),
        }])
        .emit();
        MarketEvent::WelfareSnapshot(vec![self.summary()]).emit();

        let revenue_yocto =
            escrow_yocto(revenue).unwrap_or_else(|| env::panic_str("settlement revenue overflow"));
        let fee_yocto =
            escrow_yocto(fee).unwrap_or_else(|| env::panic_str("settlement fee overflow"));
        let mut promise = Promise::new(business_profile.payout_account.clone())
            .transfer(NearToken::from_yoctonear(revenue_yocto));
        if fee > 0 {
            promise = promise.and(
                Promise::new(self.owner.clone()).transfer(NearToken::from_yoctonear(fee_yocto)),
            );
        }
        promise
    }

    /// Permissionless refund after expiry. The caller pays gas; the escrow goes
    /// back to the customer. The status transition happens before the transfer.
    pub fn refund(&mut self, proposal_id: String) -> Promise {
        let mut proposal = self
            .proposals
            .get(&proposal_id)
            .cloned()
            .unwrap_or_else(|| env::panic_str("proposal not found"));
        require!(
            proposal.status == ProposalStatus::Funded,
            "proposal is not funded"
        );
        require!(
            env::block_timestamp() > proposal.expiry.0,
            "proposal has not expired"
        );

        proposal.status = ProposalStatus::Refunded;
        self.proposals.insert(proposal_id, proposal.clone());
        let amount = escrow_yocto(proposal.total_price.0)
            .unwrap_or_else(|| env::panic_str("refund amount overflow"));
        Promise::new(proposal.customer).transfer(NearToken::from_yoctonear(amount))
    }
}

impl Contract {
    fn validate_proposal(
        &self,
        business: &AccountId,
        customer: &AccountId,
        proposal_id: &str,
        items: &[OrderItem],
        total_price: U128,
        expiry: u64,
    ) -> Result<(), String> {
        let Some(profile) = self.agents.get(business) else {
            return Err("business is not registered".to_string());
        };
        if profile.role != Role::Business {
            return Err("predecessor is not a business".to_string());
        }
        if proposal_id.is_empty() || proposal_id.len() > 128 {
            return Err("proposal_id must be 1-128 characters".to_string());
        }
        if self.proposals.contains_key(proposal_id) {
            return Err("proposal_id already exists".to_string());
        }
        if items.is_empty() || items.len() > MAX_ITEMS_PER_PROPOSAL {
            return Err(format!(
                "items must contain 1..={MAX_ITEMS_PER_PROPOSAL} entries"
            ));
        }

        for item in items {
            if item.quantity == 0 {
                return Err("item quantity must be positive".to_string());
            }
            let Some((_, menu_price)) = profile
                .menu
                .iter()
                .find(|(menu_name, _)| menu_name == &item.item_name)
            else {
                return Err(format!("item not on menu: {}", item.item_name));
            };
            if !cents_delta_ok(item.unit_price.0, menu_price.0) {
                return Err(format!(
                    "unit price is not the menu price: {}",
                    item.item_name
                ));
            }
        }

        let Some(computed_total) = order_total(items) else {
            return Err("proposal total overflow".to_string());
        };
        if !cents_delta_ok(total_price.0, computed_total) {
            return Err("total_price does not equal sum(quantity * unit_price)".to_string());
        }

        let Some(customer_profile) = self.agents.get(customer) else {
            return Err("customer is not registered".to_string());
        };
        if customer_profile.role != Role::Customer {
            return Err("customer account is not a customer".to_string());
        }
        if env::block_timestamp() >= expiry {
            return Err("proposal expiry is not in the future".to_string());
        }

        let posted_count = self
            .proposal_count_by_customer
            .get(customer)
            .copied()
            .unwrap_or(0);
        if posted_count >= MAX_PROPOSALS_PER_CUSTOMER {
            return Err("customer reached MAX_PROPOSALS_PER_CUSTOMER".to_string());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn agent_name_rules_match_account_segments() {
        assert!(valid_agent_name("b1"));
        assert!(valid_agent_name("customer_0001"));
        assert!(valid_agent_name("a-b"));
        assert!(!valid_agent_name(""));
        assert!(!valid_agent_name("-a"));
        assert!(!valid_agent_name("a-"));
        assert!(!valid_agent_name("Upper"));
        assert!(!valid_agent_name("a.b"));
        assert!(!valid_agent_name(&"a".repeat(41)));
    }

    #[test]
    fn superset_and_amenities_match_the_origin_predicate() {
        let items = vec![OrderItem {
            item_name: "Tile Grouting".to_string(),
            quantity: 1,
            unit_price: U128(13_403),
        }];
        let menu = vec![("Tile Grouting".to_string(), U128(13_403))];
        assert!(is_superset(&items, &menu));
        assert!(!is_superset(&items, &[("Missing".to_string(), U128(1))]));

        let offered = vec!["warranty".to_string(), "licensed".to_string()];
        assert!(amenities_cover(&["warranty".to_string()], &offered));
        assert!(!amenities_cover(
            &["after hours service".to_string()],
            &offered
        ));
    }
}
