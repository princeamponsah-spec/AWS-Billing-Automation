"""
Weekly AWS Cost Explorer -> AWS_Weekly_Billing_Tracker.xlsx automation.

Runs on an EventBridge weekly schedule (see README.md for the exact rule). Each run:
  1. Assumes a read-only Cost Explorer role in each of the 6 member accounts.
  2. Pulls this week's figures from Cost Explorer for each account.
  3. Downloads the master workbook from S3, writes the new week's 6 rows into the
     next blank block on the 'Weekly Entry' tab (formulas are untouched), re-uploads it.
  4. Sends a short Slack/SNS notification with a summary and any accounts that failed.

Deploy this alongside cost_explorer.py, excel_writer.py and config.py, plus an
openpyxl Lambda layer (openpyxl is not in the standard runtime) - see README.md.
"""

import datetime
import json
import logging
import os
import tempfile
import urllib.request

import boto3

import config
from cost_explorer import get_weekly_figures
from excel_writer import write_week, TrackerFullError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

s3 = boto3.client("s3")
sts = boto3.client("sts")


def _most_recent_sunday(today: datetime.date) -> datetime.date:
    """The tracker uses Sunday week-ending dates. If run on a Monday, this is
    'yesterday'; this formula works no matter which day the schedule actually fires."""
    days_since_sunday = (today.weekday() + 1) % 7  # Monday=0 ... Sunday=6 in .weekday()
    return today - datetime.timedelta(days=days_since_sunday)


def _assume_role(role_arn: str) -> boto3.Session:
    resp = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName="WeeklyBillingTrackerLambda",
    )
    creds = resp["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )


def _notify(message: str):
    if config.SLACK_WEBHOOK_URL:
        try:
            req = urllib.request.Request(
                config.SLACK_WEBHOOK_URL,
                data=json.dumps({"text": message}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            logger.exception("Slack notification failed")
    if config.SNS_TOPIC_ARN:
        try:
            boto3.client("sns").publish(
                TopicArn=config.SNS_TOPIC_ARN,
                Subject="Weekly AWS Billing Tracker update",
                Message=message,
            )
        except Exception:
            logger.exception("SNS notification failed")


def handler(event, context):
    today = datetime.date.today()
    week_ending = _most_recent_sunday(today)
    logger.info("Running weekly billing pull for week ending %s", week_ending)

    figures_by_account = {}
    failures = []

    for account_name, account_cfg in config.ACCOUNTS.items():
        try:
            session = _assume_role(account_cfg["role_arn"])
            figures_by_account[account_name] = get_weekly_figures(session, today)
            logger.info("Pulled figures for %s: %s", account_name, figures_by_account[account_name])
        except Exception as exc:
            logger.exception("Failed to pull figures for %s", account_name)
            failures.append(f"{account_name}: {exc}")

    if failures:
        # Don't write a partial week - all 6 accounts must succeed together, since the
        # sheet's formulas expect a complete 6-row block per week.
        message = (
            f"\u274C Weekly billing update for {week_ending} FAILED for "
            f"{len(failures)} account(s), so no rows were written:\n" + "\n".join(failures)
        )
        logger.error(message)
        _notify(message)
        return {"statusCode": 500, "body": message}

    with tempfile.TemporaryDirectory() as tmp:
        local_path = os.path.join(tmp, "tracker.xlsx")
        s3.download_file(config.S3_BUCKET, config.S3_KEY, local_path)

        try:
            start_row, end_row = write_week(
                local_path, week_ending, config.ACCOUNT_ORDER, figures_by_account
            )
        except TrackerFullError as exc:
            message = f"\u26A0\uFE0F {exc}"
            logger.error(message)
            _notify(message)
            return {"statusCode": 500, "body": message}

        s3.upload_file(local_path, config.S3_BUCKET, config.S3_KEY)

    total = sum(f["mtd"] for f in figures_by_account.values())
    message = (
        f"\u2705 Weekly billing tracker updated for week ending {week_ending} "
        f"(rows {start_row}-{end_row}). Combined MTD across all 6 accounts: ${total:,.2f}.\n"
        f"Open formulas will recalculate automatically next time the file is opened in Excel."
    )
    logger.info(message)
    _notify(message)
    return {"statusCode": 200, "body": message}
