// The components the checked files use but the check doesn't cover (R9, D068): shadcn's
// generated ui/ (its CLI rewrites them) and the app's own that take no contract data. Their
// props read as open here; their own files stay unchecked.
declare module '@/components/ui/*'
declare module '@/components/ai/*'
declare module '@/components/AuthImage'
declare module '@/components/DateTimePicker'
declare module '@/components/HeaderMenu'
