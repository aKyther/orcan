const start = "\n\n<!-- orcan:preferred-tools -->\n## Preferred tools\n\n";
const guidance = "\n\nStart with these tools when appropriate. Follow repository requirements and existing conventions; do not replace the project stack just to match this preference.";
const end = "\n<!-- /orcan:preferred-tools -->";

export function identityInstructions(instructions: string, tools: string): string {
  return tools.trim() ? instructions + start + tools.trim() + guidance + end : instructions;
}

export function identityFields(instructions: string): { instructions: string; tools: string } {
  const index = instructions.lastIndexOf(start);
  if (index < 0 || !instructions.endsWith(guidance + end)) return { instructions, tools: "" };
  return { instructions: instructions.slice(0, index), tools: instructions.slice(index + start.length, -(guidance + end).length) };
}
