"""
Pulls the same figures a person used to read off the AWS Billing console screenshots,
via the Cost Explorer API, for a single AWS account.

Cost Explorer is only queryable from us-east-1, and only via credentials for the
account being queried - hence the assume-role step in lambda_function.py before any
of these functions are called.
"""

import datetime
import boto3


def _month_bounds(ref_date: datetime.date):
    """Return (start_of_this_month, start_of_next_month) as date objects."""
    start_this_month = ref_date.replace(day=1)
    if start_this_month.month == 12:
        start_next_month = start_this_month.replace(year=start_this_month.year + 1, month=1)
    else:
        start_next_month = start_this_month.replace(month=start_this_month.month + 1)
    return start_this_month, start_next_month


def _prior_month_bounds(ref_date: datetime.date):
    """Return (start_of_last_month, start_of_this_month, same_period_end) where
    same_period_end is last month's date matching ref_date's day-of-month (used as the
    exclusive end of the "last month, same period" comparison window)."""
    start_this_month, _ = _month_bounds(ref_date)
    last_month_end = start_this_month  # exclusive
    if start_this_month.month == 1:
        last_month_start = start_this_month.replace(year=start_this_month.year - 1, month=12)
    else:
        last_month_start = start_this_month.replace(month=start_this_month.month - 1)
    try:
        same_period_end = last_month_start.replace(day=ref_date.day)
    except ValueError:
        # ref_date's day-of-month doesn't exist in the (shorter) previous month,
        # e.g. ref_date = 31st and last month only had 30 days - use its last day instead.
        same_period_end = last_month_end - datetime.timedelta(days=1)
    return last_month_start, last_month_end, same_period_end


def _total_unblended_cost(ce_client, start: datetime.date, end: datetime.date) -> float:
    """Total UnblendedCost for [start, end) as a single MONTHLY-granularity query."""
    if start >= end:
        return 0.0
    resp = ce_client.get_cost_and_usage(
        TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )
    results = resp.get("ResultsByTime", [])
    return sum(float(r["Total"]["UnblendedCost"]["Amount"]) for r in results)


def _cost_by_service(ce_client, start: datetime.date, end: datetime.date) -> dict:
    """{service_name: cost} for [start, end)."""
    if start >= end:
        return {}
    resp = ce_client.get_cost_and_usage(
        TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    out = {}
    for result in resp.get("ResultsByTime", []):
        for group in result.get("Groups", []):
            name = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            out[name] = out.get(name, 0.0) + amount
    return out


def _forecast_remaining_month(ce_client, start: datetime.date, end: datetime.date) -> float:
    """Forecasted UnblendedCost for [start, end). Returns 0 if the window is empty
    (e.g. we're being asked to forecast a period that has already fully elapsed)."""
    if start >= end:
        return 0.0
    resp = ce_client.get_cost_forecast(
        TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
        Metric="UNBLENDED_COST",
        Granularity="MONTHLY",
    )
    return float(resp["Total"]["Amount"])


def get_weekly_figures(assumed_session: boto3.Session, ref_date: datetime.date) -> dict:
    """
    Returns the 7 values the Weekly Entry tab needs for one account, as of ref_date
    (normally "today", the day the Lambda runs):

        mtd, last_month_same_period, forecast, last_month_total,
        highest_spend, highest_service, trend

    'trend' mirrors the AWS console's "highest service spend, trend vs prior month" -
    i.e. how much that top service's spend has moved vs the same period last month.
    """
    ce = assumed_session.client("ce", region_name="us-east-1")

    start_this_month, start_next_month = _month_bounds(ref_date)
    last_month_start, last_month_end, same_period_end = _prior_month_bounds(ref_date)

    mtd = _total_unblended_cost(ce, start_this_month, ref_date + datetime.timedelta(days=1))
    last_month_same_period = _total_unblended_cost(ce, last_month_start, same_period_end)
    last_month_total = _total_unblended_cost(ce, last_month_start, last_month_end)

    forecast_remaining = _forecast_remaining_month(
        ce, ref_date + datetime.timedelta(days=1), start_next_month
    )
    forecast_total = mtd + forecast_remaining

    this_month_by_service = _cost_by_service(ce, start_this_month, ref_date + datetime.timedelta(days=1))
    if this_month_by_service:
        highest_service = max(this_month_by_service, key=this_month_by_service.get)
        highest_spend = this_month_by_service[highest_service]
    else:
        highest_service, highest_spend = "", 0.0

    trend = None
    if highest_service:
        last_month_by_service = _cost_by_service(ce, last_month_start, same_period_end)
        prior_value = last_month_by_service.get(highest_service, 0.0)
        if prior_value > 0:
            trend = (highest_spend - prior_value) / prior_value

    return {
        "mtd": round(mtd, 2),
        "last_month_same_period": round(last_month_same_period, 2),
        "forecast": round(forecast_total, 2),
        "last_month_total": round(last_month_total, 2),
        "highest_spend": round(highest_spend, 2),
        "highest_service": highest_service,
        "trend": round(trend, 4) if trend is not None else None,
    }
