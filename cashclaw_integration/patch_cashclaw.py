import re

file_path = "/tmp/cashclaw/src/moltlaunch/cli.ts"
with open(file_path, "r") as f:
    content = f.read()

# Replace the mltl function completely with fetch calls to our gateway
new_content = """import type { Task, Bounty, WalletInfo, RegisterResult, AgentInfo } from "./types.js";

const GATEWAY_URL = "http://localhost:3778/api";

async function fetchGateway<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${GATEWAY_URL}${endpoint}`, options);
  if (!res.ok) {
    throw new Error(`Gateway error: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// --- Setup ---

export async function walletShow(): Promise<WalletInfo> {
  return { address: "0x123", balance: "0" }; // Mocked
}

export async function walletImport(key: string): Promise<WalletInfo> {
  return { address: "0x123", balance: "0" }; // Mocked
}

export interface RegisterOpts {
  name: string;
  description: string;
  skills: string[];
  price: string;
  symbol?: string;
  token?: string;
  image?: string;
  website?: string;
}

export async function registerAgent(opts: RegisterOpts): Promise<RegisterResult> {
  return { agentId: "nexus-001" }; // Mocked
}

// --- Agent lookup ---

export async function getAgentByWallet(address: string): Promise<AgentInfo | null> {
  return null;
}

// --- Task operations ---

export async function getInbox(agentId?: string): Promise<Task[]> {
  const data = await fetchGateway<{ tasks: Task[] }>(`/inbox?agent=${agentId || ''}`);
  return data.tasks;
}

export async function getTask(taskId: string): Promise<Task> {
  const data = await fetchGateway<{ task: Task }>(`/view?task=${taskId}`);
  return data.task;
}

export async function quoteTask(
  taskId: string,
  priceEth: string,
  message?: string,
): Promise<void> {
  await fetchGateway(`/quote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ taskId, priceEth, message })
  });
}

export async function declineTask(
  taskId: string,
  reason?: string,
): Promise<void> {
  await fetchGateway(`/decline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ taskId, reason })
  });
}

export async function submitWork(
  taskId: string,
  result: string,
): Promise<void> {
  await fetchGateway(`/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ taskId, result })
  });
}

export async function sendMessage(
  taskId: string,
  content: string,
): Promise<void> {
  await fetchGateway(`/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ taskId, content })
  });
}

export async function getBounties(): Promise<Bounty[]> {
  return []; // Mocked for now
}

export async function claimBounty(
  taskId: string,
  message?: string,
): Promise<void> {
  // Not used right now
}
"""

with open(file_path, "w") as f:
    f.write(new_content)

print("Patched cli.ts")
