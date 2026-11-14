//! End-to-end sandbox test: sub-account registration, soft rejection, escrow,
//! settlement, and welfare counters. Runs with sandbox tokens only.

use near_sdk::serde_json::{Value, json};
use near_workspaces::result::Result;
use near_workspaces::types::{AccountId, Gas, NearToken};
use near_workspaces::{Account, compile_project, sandbox};

const YOCTO_PER_USD_CENT: u128 = 10_000_000_000_000_000_000;
const MAX_EXPIRY: &str = "18446744073709551615";

#[tokio::test]
async fn market_soft_rejects_invalid_and_settles_valid() -> Result<()> {
    let worker = sandbox().await?;
    let wasm = compile_project(concat!(env!("CARGO_MANIFEST_DIR"), "/../contracts/market")).await?;
    let contract = worker.dev_deploy(&wasm).await?;
    contract
        .call("new")
        .args_json(json!({"fee_bps": 0}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?
        .into_result()?;

    let payout = worker.dev_create_account().await?;
    let (_customer_dev_id, customer_sk) = worker.generate_dev_account_credentials();
    let (_business_dev_id, business_sk) = worker.generate_dev_account_credentials();
    let business_key = business_sk.public_key().to_string();
    let customer_key = customer_sk.public_key().to_string();

    contract
        .call("register_agent")
        .args_json(json!({
            "agent_name": "b1",
            "public_key": business_key,
            "profile": {
                "role": "Business",
                "menu": [
                    ["Door Lock Replacement", "15445"],
                    ["Hardwood Flooring", "38328"]
                ],
                "amenities": ["multilingual staff", "business accepts credit cards"],
                "requested_total_cents": "0",
                "payout_account": payout.id().to_string()
            }
        }))
        .deposit(NearToken::from_millinear(100))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?
        .into_result()?;

    contract
        .call("register_agent")
        .args_json(json!({
            "agent_name": "c1",
            "public_key": customer_key,
            "profile": {
                "role": "Customer",
                "menu": [["Door Lock Replacement", "16899"]],
                "amenities": ["multilingual staff", "business accepts credit cards"],
                "requested_total_cents": "16899",
                "payout_account": contract.id().to_string()
            }
        }))
        .deposit(NearToken::from_millinear(100))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?
        .into_result()?;

    let business_id: AccountId = format!("b1.{}", contract.id())
        .parse()
        .expect("valid business account id");
    let customer_id: AccountId = format!("c1.{}", contract.id())
        .parse()
        .expect("valid customer account id");

    let business = Account::from_secret_key(business_id.clone(), business_sk, &worker);
    let customer = Account::from_secret_key(customer_id.clone(), customer_sk, &worker);
    worker
        .root_account()?
        .transfer_near(&business_id, NearToken::from_near(1))
        .await?
        .into_result()?;
    worker
        .root_account()?
        .transfer_near(&customer_id, NearToken::from_near(2))
        .await?
        .into_result()?;

    let business_profile: Value = contract
        .view("get_agent")
        .args_json(json!({"agent_id": business_id}))
        .await?
        .json()?;
    assert_eq!(business_profile["role"], "Business");
    assert_eq!(business_profile["menu"][0][0], "Door Lock Replacement");

    business
        .call(contract.id(), "post_proposal")
        .args_json(json!({
            "proposal_id": "invalid-1",
            "customer": customer_id.to_string(),
            "items": [{"item_name": "Unobtainium", "quantity": 1, "unit_price": "100"}],
            "total_price": "100",
            "expiry": MAX_EXPIRY
        }))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?
        .into_result()?;

    business
        .call(contract.id(), "post_proposal")
        .args_json(json!({
            "proposal_id": "invalid-price",
            "customer": customer_id.to_string(),
            "items": [{"item_name": "Door Lock Replacement", "quantity": 1, "unit_price": "15446"}],
            "total_price": "15446",
            "expiry": MAX_EXPIRY
        }))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?
        .into_result()?;

    business
        .call(contract.id(), "post_proposal")
        .args_json(json!({
            "proposal_id": "invalid-total",
            "customer": customer_id.to_string(),
            "items": [{"item_name": "Door Lock Replacement", "quantity": 1, "unit_price": "15445"}],
            "total_price": "15446",
            "expiry": MAX_EXPIRY
        }))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?
        .into_result()?;

    let welfare: Value = contract.view("get_welfare").await?.json()?;
    assert_eq!(welfare["rejected_proposals"], 3);
    let rejected: Value = contract
        .view("get_proposal")
        .args_json(json!({"proposal_id": "invalid-1"}))
        .await?
        .json()?;
    assert!(rejected.is_null());

    business
        .call(contract.id(), "post_proposal")
        .args_json(json!({
            "proposal_id": "p1",
            "customer": customer_id.to_string(),
            "items": [{"item_name": "Door Lock Replacement", "quantity": 1, "unit_price": "15445"}],
            "total_price": "15445",
            "expiry": MAX_EXPIRY
        }))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?
        .into_result()?;

    let posted: Value = contract
        .view("get_proposal")
        .args_json(json!({"proposal_id": "p1"}))
        .await?
        .json()?;
    assert_eq!(posted["status"], "Posted");
    assert_eq!(posted["total_price"], "15445");

    customer
        .call(contract.id(), "accept_proposal")
        .args_json(json!({"proposal_id": "p1"}))
        .deposit(NearToken::from_yoctonear(15_445 * YOCTO_PER_USD_CENT))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?
        .into_result()?;

    let funded: Value = contract
        .view("get_proposal")
        .args_json(json!({"proposal_id": "p1"}))
        .await?
        .json()?;
    assert_eq!(funded["status"], "Funded");

    let payout_before = payout.view_account().await?.balance;
    business
        .call(contract.id(), "settle")
        .args_json(json!({"proposal_id": "p1"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?
        .into_result()?;
    let payout_after = payout.view_account().await?.balance;
    assert_eq!(
        payout_after.as_yoctonear() - payout_before.as_yoctonear(),
        15_445 * YOCTO_PER_USD_CENT
    );

    let settled: Value = contract
        .view("get_proposal")
        .args_json(json!({"proposal_id": "p1"}))
        .await?
        .json()?;
    assert_eq!(settled["status"], "Settled");

    let trade_count: u64 = contract.view("get_trade_count").await?.json()?;
    assert_eq!(trade_count, 1);

    let welfare: Value = contract.view("get_welfare").await?.json()?;
    assert_eq!(welfare["settled_count"], 1);
    assert_eq!(welfare["needs_met_count"], 1);
    assert_eq!(welfare["purchasing_customers"], 1);
    assert_eq!(welfare["registered_customers"], 1);
    assert_eq!(welfare["purchase_completion_bps"], 10_000);
    assert_eq!(welfare["total_customer_utility_cents"], "18353");
    assert_eq!(welfare["total_business_revenue_cents"], "15445");
    assert_eq!(welfare["avg_utility_per_purchaser_cents"], "18353");

    let second_settle = business
        .call(contract.id(), "settle")
        .args_json(json!({"proposal_id": "p1"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?;
    assert!(
        second_settle.into_result().is_err(),
        "double settle must fail"
    );

    let expiry = (worker.view_block().await?.timestamp() + 2_000_000_000).to_string();
    business
        .call(contract.id(), "post_proposal")
        .args_json(json!({
            "proposal_id": "p2",
            "customer": customer_id.to_string(),
            "items": [{"item_name": "Door Lock Replacement", "quantity": 1, "unit_price": "15445"}],
            "total_price": "15445",
            "expiry": expiry
        }))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?
        .into_result()?;
    customer
        .call(contract.id(), "accept_proposal")
        .args_json(json!({"proposal_id": "p2"}))
        .deposit(NearToken::from_yoctonear(15_445 * YOCTO_PER_USD_CENT))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?
        .into_result()?;

    worker.fast_forward(10).await?;
    let stranger = worker.dev_create_account().await?;
    stranger
        .call(contract.id(), "refund")
        .args_json(json!({"proposal_id": "p2"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?
        .into_result()?;
    let refunded: Value = contract
        .view("get_proposal")
        .args_json(json!({"proposal_id": "p2"}))
        .await?
        .json()?;
    assert_eq!(refunded["status"], "Refunded");
    let second_refund = stranger
        .call(contract.id(), "refund")
        .args_json(json!({"proposal_id": "p2"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?;
    assert!(
        second_refund.into_result().is_err(),
        "double refund must fail"
    );
    let welfare_after: Value = contract.view("get_welfare").await?.json()?;
    assert_eq!(welfare_after["settled_count"], 1);
    assert_eq!(welfare_after["total_customer_utility_cents"], "18353");

    Ok(())
}
