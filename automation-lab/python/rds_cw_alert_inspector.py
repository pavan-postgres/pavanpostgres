import json
import subprocess
import textwrap
from tabulate import tabulate

WRAP_WIDTH = 60  # Wrap width for State Reason column

def get_rds_alarm_names():
    """Fetch alarm names that contain 'AWS RDS'."""
    cmd = [
        "aws", "cloudwatch", "describe-alarms",
        "--query", "MetricAlarms[].[AlarmName]",
        "--output", "text"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("Failed to fetch alarm names.")
    return [line.strip() for line in result.stdout.splitlines() if "AWS RDS" in line]

def format_multiline_row(row):
    wrapped = [
        textwrap.wrap(str(cell), WRAP_WIDTH) if i == 3 else [str(cell)]
        for i, cell in enumerate(row)
    ]
    max_lines = max(len(lines) for lines in wrapped)
    padded = [lines + [''] * (max_lines - len(lines)) for lines in wrapped]
    return list(zip(*padded))  # Each tuple is one display row

def describe_alarm_history(alert_name):
    cmd = [
        "aws", "cloudwatch", "describe-alarm-history",
        "--alarm-name", alert_name,
        "--query", "AlarmHistoryItems[?contains(HistorySummary, 'OK to ALARM')].HistoryData",
        "--output", "json"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

def main():
    final_rows = []
    rds_alarms = get_rds_alarm_names()

    for alert_name in rds_alarms:
        history_items = describe_alarm_history(alert_name)
        for raw_str in history_items:
            try:
                alarm = json.loads(raw_str)
                new_state = alarm["newState"]
                reason_data = new_state["stateReasonData"]
                start_date = reason_data.get("startDate", "N/A")
                state_value = new_state["stateValue"]
                state_reason = new_state["stateReason"]
                evaluated = reason_data.get("evaluatedDatapoints", [])

                for point in evaluated:
                    row = [
                        start_date,
                        alert_name,
                        state_value,
                        state_reason,
                        #point.get("timestamp", "N/A"),
                        #point.get("value", "N/A"),
                        #point.get("sampleCount", "N/A")
                    ]
                    final_rows.extend(format_multiline_row(row))
            except Exception:
                continue

    headers = ["Start Date", "Alert Name", "State Value", "State Reason"]
    print(tabulate(final_rows, headers=headers, tablefmt="grid", stralign="left"))

if __name__ == "__main__":
    main()
  
