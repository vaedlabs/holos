// Generated from contracts/schema by npm run contracts:types. Don't edit.

export interface TraceView {
  /**
   * @maxItems 3
   */
  agents?: ('physical' | 'nutrition' | 'mental')[]
  decisions?: Decision[]
  retries?: number
  route: ('coaching' | 'greeting' | 'meta' | 'off_topic' | 'unclear' | 'other_language') | 'crisis'
  sources?: Source[]
  steps?: TraceStep[]
  tools?: TraceTool[]
  trace_id: string
  usage: Usage
}
export interface Decision {
  action: 'allow' | 'warn' | 'block'
  offending_items?: string[]
  reason: string
  rule_id: string
  rules_version: number
}
export interface Source {
  id: string
  title: string
  url: string
}
export interface TraceStep {
  agent?: ('physical' | 'nutrition' | 'mental') | null
  duration_ms: number
  name: string
  queue_ms: number
  start_ms: number
}
export interface TraceTool {
  args: string
  duration_ms: number
  name: string
  status: 'ok' | 'error' | 'refused' | 'staged' | 'held' | 'unavailable'
}
export interface Usage {
  cost_usd: number
  tokens_in: number
  tokens_out: number
}
