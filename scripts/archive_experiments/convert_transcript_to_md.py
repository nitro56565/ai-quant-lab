"""
Convert JSONL Transcript into readable Markdown document full_conversation_history.md
"""

import os, sys, json

transcript_path = "/Users/mahesh.patil/.gemini/antigravity-cli/brain/ea72aff7-8e24-479d-849f-e439515851a6/.system_generated/logs/transcript.jsonl"
output_path = "/Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab/docs/full_conversation_history.md"
artifact_output = "/Users/mahesh.patil/.gemini/antigravity-cli/brain/ea72aff7-8e24-479d-849f-e439515851a6/full_conversation_history.md"

if not os.path.exists(transcript_path):
    print("Transcript path not found.")
    sys.exit(1)

md_lines = ["# 📜 Complete Conversation History Log\n\n"]
md_lines.append("This document contains the complete chronological record of all user prompts, system audits, and experimental findings from this session.\n\n---\n\n")

step_num = 1
with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            step_type = data.get("type", "")
            content = data.get("content", "")

            if step_type == "USER_INPUT":
                md_lines.append(f"## 👤 User Prompt #{step_num}\n\n```text\n{content}\n```\n\n")
                step_num += 1
            elif step_type == "PLANNER_RESPONSE" and content:
                # Truncate very long tool response logs if needed
                if len(content) > 3000:
                    content_disp = content[:3000] + "\n... [Content Truncated for Readability] ..."
                else:
                    content_disp = content
                md_lines.append(f"### 🤖 Assistant Response\n\n{content_disp}\n\n---\n\n")
        except Exception as e:
            continue

full_md = "".join(md_lines)

os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w", encoding="utf-8") as f:
    f.write(full_md)

with open(artifact_output, "w", encoding="utf-8") as f:
    f.write(full_md)

print("Successfully converted transcript to Markdown!")
