"""
Configuration for the AWS Weekly Billing Tracker automation.

Fill in the six AWS account IDs below. Each entry maps the exact account name string
used in the 'Weekly Entry' tab of AWS_Weekly_Billing_Tracker.xlsx to:
  - the member account's 12-digit account ID
  - the ARN of the read-only Cost Explorer role deployed in that account
    (see iam/member-account-role-*.json - the role name below must match what you
    actually name the role when you deploy it)

IMPORTANT: The keys here must exactly match the "AWS Account" column values in the
workbook (including the "AWS " prefix), or the automatically-written rows will not
line up with the account-color formatting and dropdown validation already in the sheet.
"""

ROLE_NAME = "WeeklyBillingCostExplorerReadOnly"

ACCOUNTS = {
    "AWS Main Account": {
        "account_id": "111111111111",
        "role_arn": f"arn:aws:iam::111111111111:role/{ROLE_NAME}",
    },
    "AWS Kowri Business Account": {
        "account_id": "222222222222",
        "role_arn": f"arn:aws:iam::222222222222:role/{ROLE_NAME}",
    },
    "AWS Kowri Consumer Prod Account": {
        "account_id": "333333333333",
        "role_arn": f"arn:aws:iam::333333333333:role/{ROLE_NAME}",
    },
    "AWS Kowri Consumer UAT Account": {
        "account_id": "444444444444",
        "role_arn": f"arn:aws:iam::444444444444:role/{ROLE_NAME}",
    },
    "AWS ZIM Account": {
        "account_id": "555555555555",
        "role_arn": f"arn:aws:iam::555555555555:role/{ROLE_NAME}",
    },
    "AWS MPS Account": {
        "account_id": "666666666666",
        "role_arn": f"arn:aws:iam::666666666666:role/{ROLE_NAME}",
    },
}

# Order matters: the workbook expects exactly this order within each week's 6-row block.
ACCOUNT_ORDER = list(ACCOUNTS.keys())

# --- S3 location of the master workbook -------------------------------------------------
S3_BUCKET = "your-billing-tracker-bucket"       # <-- change me
S3_KEY = "AWS_Weekly_Billing_Tracker.xlsx"      # <-- change me if you rename the file

# --- Optional notification (Slack incoming webhook or SNS topic ARN) --------------------
# Leave as None to disable. See lambda_function.py for how each is used.
SLACK_WEBHOOK_URL = None
SNS_TOPIC_ARN = None
