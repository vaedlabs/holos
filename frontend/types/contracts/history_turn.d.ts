// Generated from contracts/schema by npm run contracts:types. Don't edit.

export interface HistoryTurn {
  agents?: ('physical' | 'nutrition' | 'mental')[] | null
  content: string
  prev?: string | null
  role: 'user' | 'assistant'
  shown?: string | null
  sig?: string | null
  ts: string
}
