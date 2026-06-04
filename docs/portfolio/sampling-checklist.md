# Sampling Checklist

| Sampling item | Purpose | Minimum requirement | Privacy note |
| --- | --- | --- | --- |
| Target developer interviews | Validate whether hard-coded model choice, fallback handling, and outcome traceability are real pain points. | At least 5 Agent / workflow / internal AI tool builders. | Do not record real names, company secrets, vendor keys, prompts, or production logs. |
| Competitor screenshots | Compare routing gateways, model routers, observability tools, and FinOps alternatives. | 2 screenshots per competitor, covering decision config and observability if available. | Redact account IDs, tenant names, API keys, and internal model names. |
| Demo recording | Prove the main flow can be observed without reading code. | One complete decision -> provider invoke -> outcome report recording. | Use placeholder keys and redact terminal history. |
| Usability test | Check whether a target user understands decision, fallback, and rejection fields. | 3 participants read the portfolio or use API docs and explain the flow back. | Avoid collecting private prompts or proprietary routing policies. |
| Real usage data | Support future claims about cost, latency, reliability, or workflow impact. | At least one controlled benchmark or pilot dataset with before/after route decisions. | Aggregate data; do not publish raw requests or vendor response content. |
| Release evidence | Support claims about public delivery state. | GitHub release, demo page, or documented showcase link. | Do not call the project "launched" before release evidence exists. |
