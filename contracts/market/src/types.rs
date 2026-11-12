//! Shared state types, price constants, and the storage-key prefix enum.

use near_sdk::json_types::{I128, U128, U64};
use near_sdk::{AccountId, IntoStorageKey, near};

/// Who owns an agent sub-account.
#[near(serializers = [borsh, json])]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Role {
    Business,
    Customer,
}

/// One line of a proposal. `unit_price` is an integer number of USD cents.
#[near(serializers = [borsh, json])]
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OrderItem {
    pub item_name: String,
    pub quantity: u64,
    pub unit_price: U128,
}

/// The validation-bearing on-chain record for a registered agent.
///
/// Search and prompt text stay in the off-chain simulation; this profile keeps
/// only the fields the settlement contract checks.
#[near(serializers = [borsh, json])]
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AgentProfile {
    pub role: Role,
    /// Item name -> price in USD cents. Business: menu price. Customer: requested price.
    pub menu: Vec<(String, U128)>,
    /// Business: amenities it actually offers. Customer: amenities it requires.
    pub amenities: Vec<String>,
    /// Customer: sum of `menu` requested prices in cents. Business: zero.
    pub requested_total_cents: U128,
    /// Business: an account with a FullAccess key that receives settlement.
    /// Customer: the paying account.
    pub payout_account: AccountId,
}

/// The escrow lifecycle. Every transition is guarded on the previous state.
#[near(serializers = [borsh, json])]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProposalStatus {
    Posted,
    Funded,
    Settled,
    Refunded,
}

/// A business price commitment, before and after escrow.
#[near(serializers = [borsh, json])]
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Proposal {
    pub business: AccountId,
    pub customer: AccountId,
    pub items: Vec<OrderItem>,
    /// Integer USD cents.
    pub total_price: U128,
    /// Block timestamp in nanoseconds.
    pub expiry: U64,
    pub status: ProposalStatus,
}

/// One settled trade, appended to the on-chain trade log.
#[near(serializers = [borsh, json])]
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TradeReceipt {
    pub proposal_id: String,
    pub customer: AccountId,
    pub business: AccountId,
    pub price: U128,
    pub fee: U128,
    pub needs_met: bool,
    pub ts: U64,
}

/// Running welfare totals. Kept native because the struct is small.
#[near(serializers = [borsh, json])]
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct WelfareCounters {
    pub total_customer_utility_cents: I128,
    pub total_business_revenue_cents: U128,
    pub settled_count: u32,
    pub needs_met_count: u32,
    pub purchasing_customers: u32,
    pub registered_customers: u32,
    pub rejected_proposals: u32,
}

/// The free view returned by `get_welfare` and emitted after each settlement.
#[near(serializers = [json])]
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct WelfareSummary {
    pub total_customer_utility_cents: I128,
    pub total_business_revenue_cents: U128,
    pub needs_met_count: u32,
    pub settled_count: u32,
    pub rejected_proposals: u32,
    pub registered_customers: u32,
    pub purchasing_customers: u32,
    pub purchase_completion_bps: u32,
    pub avg_utility_per_purchaser_cents: I128,
}

/// Demo peg: 1 NEAR = $1000 = 100,000 cents.
pub const CENTS_PER_NEAR: u128 = 100_000;
pub const YOCTO_PER_NEAR: u128 = 1_000_000_000_000_000_000_000_000;
/// Derived peg: 1 cent = 1e19 yoctoNEAR.
pub const YOCTO_PER_USD_CENT: u128 = YOCTO_PER_NEAR / CENTS_PER_NEAR;
const _: () = assert!(YOCTO_PER_USD_CENT == 10_000_000_000_000_000_000);

/// Integer cents only: the origin rejects `abs(delta) >= 0.01` dollars, so any
/// nonzero cent delta is invalid here.
pub const MAX_PRICE_DELTA_CENTS: u128 = 0;
pub const MAX_MENU: usize = 50;
pub const MAX_AMENITIES: usize = 20;
pub const MAX_ITEMS_PER_PROPOSAL: usize = 10;
pub const MAX_PROPOSALS_PER_CUSTOMER: u32 = 20;
/// Five minutes, used when the origin proposal has no `expiry_time`.
pub const PROPOSAL_TTL_NS: u64 = 300_000_000_000;

/// NEP-642 account creation cost, transferred to every new agent sub-account.
pub const ACCOUNT_CREATION_YOCTO: u128 = 7_000_000_000_000_000_000_000;
/// Fixed storage quote for an agent profile (menu, amenities, keys, map entry)
/// plus a proposal reserve. The contract charges this instead of measuring a
/// storage delta across a collection write, whose cache flushes on Drop.
pub const AGENT_REGISTRATION_BYTES: u128 = 4_000;

/// Storage prefixes stay one byte to keep keys short.
pub enum StorageKey {
    Agents,
    Proposals,
    Trades,
    PaidCents,
    NeedsMet,
    ProposalCounts,
}

impl IntoStorageKey for StorageKey {
    fn into_storage_key(self) -> Vec<u8> {
        match self {
            StorageKey::Agents => b"a".to_vec(),
            StorageKey::Proposals => b"p".to_vec(),
            StorageKey::Trades => b"t".to_vec(),
            StorageKey::PaidCents => b"c".to_vec(),
            StorageKey::NeedsMet => b"n".to_vec(),
            StorageKey::ProposalCounts => b"q".to_vec(),
        }
    }
}

/// Exact-cent comparison used by both proposal price checks.
pub(crate) fn cents_delta_ok(offered: u128, agreed: u128) -> bool {
    offered.abs_diff(agreed) <= MAX_PRICE_DELTA_CENTS
}


/// Sum of `quantity * unit_price` with checked arithmetic.
pub(crate) fn order_total(items: &[OrderItem]) -> Option<u128> {
    let mut total: u128 = 0;
    for item in items {
        let line = item.unit_price.0.checked_mul(u128::from(item.quantity))?;
        total = total.checked_add(line)?;
    }
    Some(total)
}

/// Escrow amount for a cent-denominated total.
pub(crate) fn escrow_yocto(total_cents: u128) -> Option<u128> {
    total_cents.checked_mul(YOCTO_PER_USD_CENT)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn peg_is_exactly_one_e19_yocto_per_cent() {
        assert_eq!(CENTS_PER_NEAR, 100_000);
        assert_eq!(YOCTO_PER_USD_CENT, 10_000_000_000_000_000_000);
        assert_eq!(YOCTO_PER_USD_CENT * CENTS_PER_NEAR, YOCTO_PER_NEAR);
    }

    #[test]
    fn exact_cents_accepts_equal_and_rejects_one_cent() {
        assert!(cents_delta_ok(41_915, 41_915));
        assert!(!cents_delta_ok(41_915, 41_914));
        assert!(!cents_delta_ok(41_914, 41_915));
        assert!(cents_delta_ok(0, 0));
    }

    #[test]
    fn order_total_uses_quantity_and_checked_math() {
        let items = vec![
            OrderItem {
                item_name: "Door Lock Replacement".to_string(),
                quantity: 1,
                unit_price: U128(15_445),
            },
            OrderItem {
                item_name: "Mulch Delivery".to_string(),
                quantity: 2,
                unit_price: U128(29_639),
            },
        ];
        assert_eq!(order_total(&items), Some(15_445 + 2 * 29_639));
        assert_eq!(order_total(&[]), Some(0));
    }

    #[test]
    fn escrow_is_exact_at_demo_prices() {
        assert_eq!(escrow_yocto(41_915), Some(419_150_000_000_000_000_000_000));
        assert_eq!(escrow_yocto(0), Some(0));
        assert_eq!(escrow_yocto(u128::MAX), None);
    }

    #[test]
    fn caps_match_the_doc() {
        assert_eq!(MAX_MENU, 50);
        assert_eq!(MAX_AMENITIES, 20);
        assert_eq!(MAX_ITEMS_PER_PROPOSAL, 10);
        assert_eq!(MAX_PROPOSALS_PER_CUSTOMER, 20);
        assert_eq!(PROPOSAL_TTL_NS, 300_000_000_000);
    }

    #[test]
    fn order_total_reports_overflow_instead_of_wrapping() {
        let items = vec![OrderItem {
            item_name: "overflow".to_string(),
            quantity: u64::MAX,
            unit_price: U128(u128::MAX),
        }];
        assert_eq!(order_total(&items), None);
    }
}
