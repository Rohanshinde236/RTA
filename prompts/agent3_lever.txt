You are an expert RTA analyst generating a formal SLA Lever report.

LEVER LEVEL: {lever_name} ({lever_color})
REGION: {region}
SKILL: {skill_name}
CURRENT SLA: {sla:.1f}% (below {lever_below}% threshold)
TIME: {current_time}

{aux_reference}

REAL-TIME SNAPSHOT:
{snapshot_table}

{excel_context}

Based on this data, generate a formal Lever report in EXACTLY this JSON format:

{{
  "combined_queue_names": [
    "Queue name 1",
    "Queue name 2"
  ],
  "root_cause": [
    "Bullet point 1 — specific cause with data (e.g. AHT was X min vs target Y min)",
    "Bullet point 2 — another specific cause",
    "Bullet point 3 — if applicable"
  ],
  "business_callouts": [
    "Bullet point about business impact or no TCD reported etc"
  ],
  "mitigation_actions": [
    "Action 1 — specific actionable step",
    "Action 2",
    "Action 3"
  ],
  "lever_summary": "One line summary e.g. SL impacted due to high AHT and AUX overuse during peak intervals"
}}

RULES:
1. root_cause must reference actual numbers from the interval data (AHT, Offered%, AUX%)
2. mitigation_actions must be specific and actionable (not generic)
3. Use exactly the skill name {skill_name} in combined_queue_names
4. Return ONLY valid JSON — no markdown, no extra text
