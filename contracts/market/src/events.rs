//! NEP-297 events for the settlement market.
//!
//! The `#[near(event_json(...))]` derive renames event names to snake_case and
//! emits `EVENT_JSON:{"standard":...,"version":...,"event":...,"data":[...]}`.

use crate::types::{Role, WelfareSummary};
use near_sdk::json_types::{I128, U128};
use near_sdk::{AccountId, near};

#[near(serializers = [json])]
#[derive(Clone, Debug)]
pub struct AgentRegisteredData {
    pub agent_id: AccountId,
    pub role: Role,
}

#[near(serializers = [json])]
#[derive(Clone, Debug)]
pub struct ProposalPostedData {
    pub proposal_id: String,
    pub business: AccountId,
    pub customer: AccountId,
    pub total_price_cents: U128,
}

#[near(serializers = [json])]
#[derive(Clone, Debug)]
pub struct ProposalAcceptedData {
    pub proposal_id: String,
    pub customer: AccountId,
    pub amount_yocto: U128,
}

#[near(serializers = [json])]
#[derive(Clone, Debug)]
pub struct TradeSettledData {
    pub proposal_id: String,
    pub customer: AccountId,
    pub business: AccountId,
    pub price_cents: U128,
    pub fee_cents: U128,
    pub needs_met: bool,
    pub customer_utility_delta_cents: I128,
    pub business_revenue_delta_cents: U128,
}

#[near(serializers = [json])]
#[derive(Clone, Debug)]
pub struct ProposalRejectedData {
    pub proposal_id: String,
    pub business: AccountId,
    pub customer: AccountId,
    pub reason: String,
}

#[near(event_json(standard = "ekklesia-market"))]
pub enum MarketEvent {
    #[event_version("1.0.0")]
    AgentRegistered(Vec<AgentRegisteredData>),
    #[event_version("1.0.0")]
    ProposalPosted(Vec<ProposalPostedData>),
    #[event_version("1.0.0")]
    ProposalAccepted(Vec<ProposalAcceptedData>),
    #[event_version("1.0.0")]
    TradeSettled(Vec<TradeSettledData>),
    #[event_version("1.0.0")]
    ProposalRejected(Vec<ProposalRejectedData>),
    #[event_version("1.0.0")]
    WelfareSnapshot(Vec<WelfareSummary>),
}
