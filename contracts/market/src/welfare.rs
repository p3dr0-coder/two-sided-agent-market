//! Free welfare views derived from the running counters.

use crate::Contract;
use crate::ContractExt;
use crate::types::{AgentProfile, Proposal, WelfareSummary};
use near_sdk::json_types::I128;
use near_sdk::{AccountId, near};

#[near]
impl Contract {
    pub fn get_welfare(&self) -> WelfareSummary {
        self.summary()
    }

    pub fn get_proposal(&self, proposal_id: String) -> Option<Proposal> {
        self.proposals.get(&proposal_id).cloned()
    }

    pub fn get_agent(&self, agent_id: AccountId) -> Option<AgentProfile> {
        self.agents.get(&agent_id).cloned()
    }

    pub fn get_trade_count(&self) -> u64 {
        u64::from(self.trade_log.len())
    }
}

impl Contract {
    pub(crate) fn summary(&self) -> WelfareSummary {
        let counters = &self.welfare;
        let purchase_completion_bps = counters
            .purchasing_customers
            .saturating_mul(10_000)
            .checked_div(counters.registered_customers)
            .unwrap_or(0);
        let avg_utility_per_purchaser_cents = if counters.purchasing_customers == 0 {
            I128(0)
        } else {
            I128(
                counters.total_customer_utility_cents.0 / i128::from(counters.purchasing_customers),
            )
        };
        WelfareSummary {
            total_customer_utility_cents: counters.total_customer_utility_cents,
            total_business_revenue_cents: counters.total_business_revenue_cents,
            needs_met_count: counters.needs_met_count,
            settled_count: counters.settled_count,
            rejected_proposals: counters.rejected_proposals,
            registered_customers: counters.registered_customers,
            purchasing_customers: counters.purchasing_customers,
            purchase_completion_bps,
            avg_utility_per_purchaser_cents,
        }
    }
}
