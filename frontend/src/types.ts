export type Effort = "off" | "minimal" | "low" | "medium" | "high";

export type MessageStatus = "complete" | "streaming" | "error" | "cancelled" | "interrupted";

export type ProviderState = "ready" | "no_provider" | "permission_required" | "no_models" | "error";

export interface ModelInfo {
  id: string;
  provider: string;
  label: string;
}

export interface Usage {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  reasoning_tokens: number | null;
}

export interface Message {
  id: string;
  chat_id: string;
  seq: number;
  role: "user" | "assistant";
  content: string;
  reasoning: string;
  status: MessageStatus;
  model: string | null;
  effort: Effort | null;
  error: string | null;
  usage: Usage | null;
  created_at: string;
}

export interface Chat {
  id: string;
  title: string;
  model: string | null;
  effort: Effort;
  created_at: string;
  updated_at: string;
}

export interface ChatSummary {
  id: string;
  title: string;
  updated_at: string;
  snippet: string | null;
}

export interface ShareRef {
  token: string;
  url: string;
}

export interface ChatDetail {
  chat: Chat;
  messages: Message[];
  share: ShareRef | null;
}

export interface StatusResponse {
  state: ProviderState;
  models: ModelInfo[];
  defaults: { model: string | null; effort: Effort };
  dashboard_url: string;
  provider_repo_url: string;
  detail: string | null;
  grant_url: string | null;
  provider: { app_name: string; url: string } | null;
}

export interface TurnResponse {
  user_message: Message;
  assistant_message: Message;
}

export interface SharedMessage {
  role: string;
  content: string;
  reasoning: string;
  model: string | null;
  created_at: string;
}

export interface SharedChat {
  title: string;
  created_at: string;
  updated_at: string;
  messages: SharedMessage[];
}

export const EFFORT_OPTIONS: { value: Effort; label: string }[] = [
  { value: "off", label: "No reasoning" },
  { value: "minimal", label: "Minimal" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];
