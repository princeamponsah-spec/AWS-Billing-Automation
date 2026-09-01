# AWS Weekly Billing Tracker — Automation

Pulls the same figures your team was reading off the AWS Billing console screenshots
each week straight from the Cost Explorer API, and writes them into the existing
`AWS_Weekly_Billing_Tracker.xlsx` — no manual typing, no screenshots.

## How it works

```
EventBridge (weekly schedule)
        │
        ▼
   Lambda function  ──assume role──▶  Cost Explorer in each of the 6 member accounts
        │
        ▼
  Download tracker.xlsx from S3
  Write this week's 6 rows (columns A–I only — every formula is left untouched)
  Upload tracker.xlsx back to S3
        │
        ▼
  Slack / SNS notification: "✅ done" or "❌ which account failed"
```

The workbook's own formulas (Weekly Spend, WoW %, Dashboard, Summary, everything)
recalculate automatically the next time someone opens the file in Excel — the Lambda
never needs to touch them.

## One-time setup

### 1. Put the workbook in S3
Create an S3 bucket (or use an existing one) and upload the current
`AWS_Weekly_Billing_Tracker.xlsx` to it. This S3 copy becomes the source of truth;
whoever needs the latest numbers downloads it from there (or you wire up a sync to
SharePoint/Google Drive/Teams separately — that part is outside this Lambda's scope).

Update `config.py`:
```python
S3_BUCKET = "your-billing-tracker-bucket"
S3_KEY = "AWS_Weekly_Billing_Tracker.xlsx"
```

### 2. Create the read-only role in each of the 6 member accounts
In **each** of the 6 AWS accounts (Main, Kowri Business, Kowri Consumer Prod, Kowri
Consumer UAT, ZIM, MPS), create an IAM role named `WeeklyBillingCostExplorerReadOnly`:

- **Trust policy:** `iam/member-account-role-trust-policy.json` — edit the
  `Principal.AWS` ARN to your Lambda execution role's ARN (from step 4).
- **Permissions policy:** `iam/member-account-role-permissions-policy.json` — as-is,
  it only grants `ce:GetCostAndUsage`, `ce:GetCostForecast`, `ce:GetDimensionValues`.

Since all 6 accounts are in one AWS Organization, the fastest way to do this is a
**CloudFormation StackSet** targeting your Organizational Unit, rather than clicking
through the IAM console 6 times — ask your AWS admin if you're not sure how.

### 3. Fill in `config.py`
Replace the placeholder 12-digit account IDs with your real ones. The dictionary keys
(`"AWS Main Account"`, etc.) must match the account names already used in the
workbook's `Weekly Entry` tab exactly.

### 4. Create the Lambda execution role (in whichever account hosts the Lambda)
- **Trust policy:** `iam/lambda-execution-role-trust-policy.json`
- **Permissions policy:** `iam/lambda-execution-role-permissions-policy.json` — edit
  the 6 `Resource` ARNs to match the role ARNs from step 2, and the S3 bucket/key.

### 5. Build the openpyxl layer
Lambda's Python runtime doesn't include `openpyxl`, so it needs to be packaged as a
layer:
```bash
bash build_layer.sh
```
Upload the resulting `openpyxl-layer.zip` as a new Lambda layer (Python 3.12 runtime).

### 6. Create the Lambda function
- Runtime: Python 3.12
- Handler: `lambda_function.handler`
- Upload `lambda_function.py`, `cost_explorer.py`, `excel_writer.py`, `config.py` as
  the function code (zip them together)
- Attach the openpyxl layer from step 5
- Attach the execution role from step 4
- Timeout: at least 60 seconds (Cost Explorer calls across 6 accounts + S3 round-trip)
- Memory: 256 MB is plenty

### 7. Schedule it with EventBridge
Create an EventBridge Scheduler rule (or a classic EventBridge rule) that triggers the
Lambda weekly, e.g. every Monday at 06:00 UTC:
```
cron(0 6 ? * MON *)
```
Run it the morning after each reporting week ends, matching your existing Monday
TechOps Weekly Snapshot meeting cadence.

### 8. (Optional) Turn on notifications
Set `SLACK_WEBHOOK_URL` or `SNS_TOPIC_ARN` in `config.py` to get a message each run —
either a ✅ summary or a ❌ listing exactly which account's Cost Explorer call failed.

## Testing it

Trigger the Lambda manually from the console with an empty test event (`{}`) before
relying on the schedule. Check CloudWatch Logs for the per-account figures it pulled,
and confirm the new week's 6 rows appear correctly in the downloaded workbook.

## Known limitations (by design, not oversights)

- **All-or-nothing per week.** If Cost Explorer fails for even one of the 6 accounts,
  no rows are written at all that week — the workbook's formulas expect complete
  6-row blocks, so a partial week would silently corrupt the Weekly Spend math for
  every account. You'll get a failure notification naming the account instead.
- **The tracker has a fixed number of pre-built future weeks** (currently enough for
  about 4–5 months of runway). When it runs out, the Lambda will fail loudly with a
  clear message rather than guessing how to extend the underlying formulas — at that
  point, regenerate the tracker with more weeks the same way it was first built.
- **Week-ending date** is always computed as "the most recent Sunday," matching the
  convention already used in the sheet. If your reporting week ever changes, update
  `_most_recent_sunday()` in `lambda_function.py`.
- This does **not** attempt to recreate the "Service Breakdown" tab's fine-grained
  service data — that came from a differently-scoped AWS report and isn't something
  the standard Cost Explorer API reproduces 1:1. This automation covers the Weekly
  Entry tab (the tracker's primary source of truth) only.
