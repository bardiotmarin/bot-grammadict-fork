import yaml

config_path = "accounts/mon_compte/config.yml"

with open(config_path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)

lines = []
for k, v in data.items():
    if isinstance(v, list):
        # Format list as inline string [item1, item2]
        # Ensure items with special characters or spaces are quoted safely if needed
        items_str = ", ".join(f'"{str(i)}"' if " " in str(i) or "-" in str(i) or "'" in str(i) else str(i) for i in v)
        lines.append(f"{k}: [{items_str}]")
    elif isinstance(v, bool):
        lines.append(f"{k}: {'true' if v else 'false'}")
    else:
        lines.append(f"{k}: {v}")

with open(config_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print("Clean YAML config written!")
