//! ekklesia-market: native-NEAR escrow plus on-chain welfare counters for a
//! two-sided agent market.
//!
//! Every agent is a sub-account of this contract with a scoped key. Businesses
//! commit prices through `post_proposal`, customers escrow an exact deposit in
//! `accept_proposal`, businesses pull the payout with `settle`, and anyone may
//! `refund` an expired-but-unsettled escrow. Welfare is a port of the origin
//! marketplace analytics formula in integer USD cents.

mod events;
mod settlement;
mod types;
mod welfare;

use crate::types::{
    AgentProfile, Proposal, StorageKey, TradeReceipt, WelfareCounters,
};
use near_sdk::json_types::U128;
use near_sdk::store::{LookupMap, LookupSet, Vector};
use near_sdk::{AccountId, PanicOnDefault, env, near, require};

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Contract {
    pub(crate) owner: AccountId,
    pub(crate) fee_bps: u16,
    pub(crate) agents: LookupMap<AccountId, AgentProfile>,
    pub(crate) proposals: LookupMap<String, Proposal>,
    pub(crate) trade_log: Vector<TradeReceipt>,
    pub(crate) paid_cents_by_customer: LookupMap<AccountId, U128>,
    pub(crate) customers_needs_met: LookupSet<AccountId>,
    pub(crate) proposal_count_by_customer: LookupMap<AccountId, u32>,
    pub(crate) welfare: WelfareCounters,
}

#[near]
impl Contract {
    /// Create the market. `fee_bps` is fixed at deployment; zero keeps
    /// settlement revenue equal to the origin's business utility definition.
    #[init]
    pub fn new(fee_bps: u16) -> Self {
        require!(fee_bps <= 10_000, "fee_bps must be at most 10000");
        Self {
            owner: env::predecessor_account_id(),
            fee_bps,
            agents: LookupMap::new(StorageKey::Agents),
            proposals: LookupMap::new(StorageKey::Proposals),
            trade_log: Vector::new(StorageKey::Trades),
            paid_cents_by_customer: LookupMap::new(StorageKey::PaidCents),
            customers_needs_met: LookupSet::new(StorageKey::NeedsMet),
            proposal_count_by_customer: LookupMap::new(StorageKey::ProposalCounts),
            welfare: WelfareCounters::default(),
        }
    }
}
