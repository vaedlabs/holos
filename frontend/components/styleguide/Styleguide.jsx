'use client'

// Every theme role and shadcn component on one page, so a theme.css edit can be checked at a glance
// in light and dark before looking through the app (R7). Dev only: app/styleguide/page.js.
import { useState } from 'react'
import NumberFlow from '@number-flow/react'
import { Check, Dumbbell, Info, Salad, Sparkles, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from '@/components/ui/drawer'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Progress } from '@/components/ui/progress'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import ChatPreview from './ChatPreview'

// Class names are written out in full so Tailwind finds them
const SURFACES = [
  { role: 'background', className: 'bg-background' },
  { role: 'card', className: 'bg-card' },
  { role: 'raised', className: 'bg-raised' },
  { role: 'primary-tint', className: 'bg-primary-tint' },
  { role: 'primary', className: 'bg-primary' },
  { role: 'border', className: 'bg-border' },
  { role: 'input', className: 'bg-input' },
  { role: 'crisis-background', className: 'bg-crisis-background' },
]

const TEXTS = [
  { role: 'foreground', className: 'text-foreground' },
  { role: 'foreground-secondary', className: 'text-foreground-secondary' },
  { role: 'muted-foreground', className: 'text-muted-foreground' },
  { role: 'primary', className: 'text-primary' },
  { role: 'destructive', className: 'text-destructive' },
  { role: 'fitness', className: 'text-fitness' },
  { role: 'nutrition', className: 'text-nutrition' },
  { role: 'mind', className: 'text-mind' },
]

const TYPE_SCALE = [
  { name: 'text-3xl', className: 'text-3xl font-heading font-bold' },
  { name: 'text-2xl', className: 'text-2xl font-heading font-bold' },
  { name: 'text-xl', className: 'text-xl font-heading font-semibold' },
  { name: 'text-lg', className: 'text-lg' },
  { name: 'text-base', className: 'text-base' },
  { name: 'text-sm', className: 'text-sm' },
  { name: 'text-xs', className: 'text-xs' },
]

const RADII = [
  { name: 'rounded-sm', className: 'rounded-sm' },
  { name: 'rounded-md', className: 'rounded-md' },
  { name: 'rounded-lg (--radius)', className: 'rounded-lg' },
  { name: 'rounded-xl (cards)', className: 'rounded-xl' },
  { name: 'rounded-2xl', className: 'rounded-2xl' },
]

const FOODS = ['Dal tadka', 'Paneer tikka', 'Masala dosa', 'Greek yoghurt', 'Oats with banana']

function Section({ title, children }) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="m-0 font-heading text-xl font-semibold">{title}</h2>
      {children}
    </section>
  )
}

function Row({ children }) {
  return <div className="flex flex-wrap items-center gap-3">{children}</div>
}

export default function Styleguide({ streams }) {
  const [calories, setCalories] = useState(1840)
  const [food, setFood] = useState('')

  return (
    <div className="min-h-dvh">
      <main className="mx-auto flex w-full max-w-page flex-col gap-12 px-4 py-10 sm:px-8">
        <header className="flex flex-col gap-2">
          <h1 className="m-0 font-heading text-3xl font-bold">Holos styleguide</h1>
          <p className="max-w-chat text-foreground-secondary">
            Every role and component from <code className="font-mono text-sm">app/theme.css</code>.
            Switch the device between light and dark to check both modes. Dev only.
          </p>
        </header>

        <Section title="Chat">
          <ChatPreview streams={streams} />
        </Section>

        <Section title="Colour roles">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {SURFACES.map((s) => (
              <div key={s.role} className="flex flex-col gap-1.5">
                <div className={`h-14 rounded-lg border ${s.className}`} />
                <span className="font-mono text-xs text-muted-foreground">{s.role}</span>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {['bg-background', 'bg-card', 'bg-raised'].map((surface) => (
              <div key={surface} className={`flex flex-col gap-1 rounded-xl border p-4 ${surface}`}>
                <span className="font-mono text-xs text-muted-foreground">on {surface.slice(3)}</span>
                {TEXTS.map((t) => (
                  <span key={t.role} className={t.className}>
                    {t.role}
                  </span>
                ))}
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-crisis-border bg-crisis-background p-4 text-crisis-foreground">
            Crisis reply: fixed colours, outside the brand roles.
          </div>
        </Section>

        <Section title="Type">
          <div className="flex flex-col gap-2">
            {TYPE_SCALE.map((t) => (
              <div key={t.name} className="flex items-baseline gap-4">
                <span className="w-20 shrink-0 font-mono text-xs text-muted-foreground">{t.name}</span>
                <span className={t.className}>One coach for training, food and how you feel</span>
              </div>
            ))}
            <div className="flex items-baseline gap-4">
              <span className="w-20 shrink-0 font-mono text-xs text-muted-foreground">font-mono</span>
              <span className="font-mono">490 kcal · 30 min · 6:59 am</span>
            </div>
          </div>
        </Section>

        <Section title="Corners and elevation">
          <Row>
            {RADII.map((r) => (
              <div key={r.name} className="flex flex-col items-center gap-1.5">
                <div className={`size-16 border bg-card ${r.className}`} />
                <span className="font-mono text-xs text-muted-foreground">{r.name}</span>
              </div>
            ))}
          </Row>
          <Row>
            <div className="rounded-xl bg-card p-5 shadow-card">shadow-card</div>
            <div className="rounded-xl bg-popover p-5 shadow-popover">shadow-popover</div>
          </Row>
        </Section>

        <Section title="Buttons">
          <Row>
            <Button>Log it</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="outline">Don&apos;t log</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="destructive">
              <Trash2 /> Delete
            </Button>
            <Button variant="link">Link</Button>
            <Button disabled>Disabled</Button>
          </Row>
          <Row>
            <Button size="sm">Small</Button>
            <Button size="lg">Large</Button>
            <Button size="icon" aria-label="Info">
              <Info />
            </Button>
            <Button disabled>
              <Spinner /> Saving
            </Button>
          </Row>
        </Section>

        <Section title="Forms">
          <div className="grid max-w-chat grid-cols-1 gap-6 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="sg-email">Email</FieldLabel>
              <Input id="sg-email" type="email" placeholder="you@example.com" />
              <FieldDescription>We only use it to sign you in.</FieldDescription>
            </Field>
            <Field data-invalid="true">
              <FieldLabel htmlFor="sg-pw">Password</FieldLabel>
              <Input id="sg-pw" type="password" aria-invalid="true" />
              <FieldError>That email and password don&apos;t match.</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="sg-weight">Weight</FieldLabel>
              <InputGroup>
                <InputGroupInput id="sg-weight" inputMode="decimal" placeholder="68" />
                <InputGroupAddon align="inline-end">kg</InputGroupAddon>
              </InputGroup>
            </Field>
            <Field>
              <FieldLabel htmlFor="sg-goal">Goal</FieldLabel>
              <Select>
                <SelectTrigger id="sg-goal" className="w-full">
                  <SelectValue placeholder="Pick a goal" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="strength">Build strength</SelectItem>
                  <SelectItem value="weight">Lose weight</SelectItem>
                  <SelectItem value="stress">Manage stress</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field className="sm:col-span-2">
              <FieldLabel htmlFor="sg-notes">Notes</FieldLabel>
              <Textarea id="sg-notes" placeholder="A meal, a workout, how you feel…" />
            </Field>
          </div>
          <Row>
            <div className="flex items-center gap-2">
              <Checkbox id="sg-check" defaultChecked />
              <Label htmlFor="sg-check">Remind me</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch id="sg-switch" />
              <Label htmlFor="sg-switch">Weekly summary</Label>
            </div>
            <RadioGroup defaultValue="kg" className="flex gap-4" aria-label="Units">
              <div className="flex items-center gap-2">
                <RadioGroupItem value="kg" id="sg-kg" />
                <Label htmlFor="sg-kg">kg</Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="lb" id="sg-lb" />
                <Label htmlFor="sg-lb">lb</Label>
              </div>
            </RadioGroup>
          </Row>
          <Chips />
          <div className="max-w-sm rounded-xl border">
            <Command>
              <CommandInput placeholder="Search foods…" />
              <CommandList>
                <CommandEmpty>No food by that name.</CommandEmpty>
                <CommandGroup heading="Foods">
                  {FOODS.map((f) => (
                    <CommandItem key={f} value={f} onSelect={() => setFood(f)}>
                      {f}
                    </CommandItem>
                  ))}
                </CommandGroup>
              </CommandList>
            </Command>
          </div>
          {food && <p className="text-sm text-foreground-secondary">Picked: {food}</p>}
        </Section>

        <Section title="Feedback">
          <Row>
            <Badge>Logged</Badge>
            <Badge variant="secondary">Held</Badge>
            <Badge variant="outline">Optional</Badge>
            <Badge variant="destructive">Failed</Badge>
            <Badge variant="outline" className="text-fitness">
              <Dumbbell /> Exercise coach
            </Badge>
            <Badge variant="outline" className="text-nutrition">
              <Salad /> Nutrition coach
            </Badge>
            <Badge variant="outline" className="text-mind">
              <Sparkles /> Mind coach
            </Badge>
          </Row>
          <div className="grid max-w-chat gap-3">
            <Alert>
              <Info />
              <AlertTitle>Check before logging</AlertTitle>
              <AlertDescription>You didn&apos;t say a time, so check this one.</AlertDescription>
            </Alert>
            <Alert variant="destructive">
              <Info />
              <AlertTitle>Couldn&apos;t save</AlertTitle>
              <AlertDescription>The connection dropped. Your entry is still here.</AlertDescription>
            </Alert>
          </div>
          <Row>
            <Button variant="outline" onClick={() => toast.success('Logged: Running · 30 min')}>
              Success toast
            </Button>
            <Button variant="outline" onClick={() => toast.error('Couldn’t delete that entry')}>
              Error toast
            </Button>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline">Tooltip</Button>
              </TooltipTrigger>
              <TooltipContent>Who answers your message</TooltipContent>
            </Tooltip>
          </Row>
          <div className="flex max-w-sm flex-col gap-3">
            <Progress value={66} aria-label="Onboarding progress" />
            <div className="flex items-center gap-3">
              <Skeleton className="size-10 rounded-full" />
              <div className="flex flex-1 flex-col gap-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            </div>
          </div>
          <Empty className="max-w-chat border">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <Salad />
              </EmptyMedia>
              <EmptyTitle>No meals today</EmptyTitle>
              <EmptyDescription>Tell the coach what you ate and it shows up here.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        </Section>

        <Section title="Numbers">
          <Row>
            <span className="font-mono text-3xl">
              <NumberFlow value={calories} /> kcal
            </span>
            <Button variant="outline" onClick={() => setCalories((prev) => prev + 245)}>
              Add a meal
            </Button>
            <Button variant="ghost" onClick={() => setCalories(() => 1840)}>
              Reset
            </Button>
          </Row>
        </Section>

        <Section title="Overlays">
          <Row>
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="outline">Dialog</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Edit entry</DialogTitle>
                  <DialogDescription>Change the time or the amount.</DialogDescription>
                </DialogHeader>
                <Input aria-label="When" defaultValue="Today, 6:59 am" />
                <DialogFooter>
                  <Button>Save</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline">Alert dialog</Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete this meal?</AlertDialogTitle>
                  <AlertDialogDescription>It comes off today&apos;s totals. You can&apos;t undo this.</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Keep it</AlertDialogCancel>
                  <AlertDialogAction variant="destructive">Delete</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline">Sheet (desktop logs)</Button>
              </SheetTrigger>
              <SheetContent>
                <SheetHeader>
                  <SheetTitle>Today&apos;s logs</SheetTitle>
                  <SheetDescription>Workouts, meals and practices.</SheetDescription>
                </SheetHeader>
              </SheetContent>
            </Sheet>
            <Drawer>
              <DrawerTrigger asChild>
                <Button variant="outline">Drawer (phone logs)</Button>
              </DrawerTrigger>
              <DrawerContent>
                <DrawerHeader>
                  <DrawerTitle>Today&apos;s logs</DrawerTitle>
                  <DrawerDescription>Workouts, meals and practices.</DrawerDescription>
                </DrawerHeader>
                <div className="h-40" />
              </DrawerContent>
            </Drawer>
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline">Popover</Button>
              </PopoverTrigger>
              <PopoverContent>Holos checks every workout and meal against your profile.</PopoverContent>
            </Popover>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline">Menu</Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuLabel>Account</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem>Profile</DropdownMenuItem>
                <DropdownMenuItem>Preferences</DropdownMenuItem>
                <DropdownMenuItem variant="destructive">Sign out</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </Row>
        </Section>

        <Section title="Structure">
          <Card className="max-w-sm">
            <CardHeader>
              <CardTitle>Running</CardTitle>
              <CardDescription>Check before logging</CardDescription>
            </CardHeader>
            <CardContent className="font-mono text-sm text-foreground-secondary">30 min · 4 km</CardContent>
            <CardFooter className="gap-2">
              <Button>Log it</Button>
              <Button variant="outline">Don&apos;t log</Button>
            </CardFooter>
          </Card>
          <Tabs defaultValue="workouts" className="max-w-chat">
            <TabsList>
              <TabsTrigger value="workouts">Workouts</TabsTrigger>
              <TabsTrigger value="meals">Meals</TabsTrigger>
              <TabsTrigger value="mind">Mind</TabsTrigger>
            </TabsList>
            <TabsContent value="workouts">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Exercise</TableHead>
                    <TableHead>Time</TableHead>
                    <TableHead className="text-right">Duration</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell>Running</TableCell>
                    <TableCell className="font-mono">6:59 am</TableCell>
                    <TableCell className="text-right font-mono">30 min</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Push-ups</TableCell>
                    <TableCell className="font-mono">7:40 am</TableCell>
                    <TableCell className="text-right font-mono">10 min</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TabsContent>
            <TabsContent value="meals">No meals yet.</TabsContent>
            <TabsContent value="mind">No practices yet.</TabsContent>
          </Tabs>
          <Accordion type="single" collapsible className="max-w-chat">
            <AccordionItem value="why">
              <AccordionTrigger>Why does Holos ask about injuries?</AccordionTrigger>
              <AccordionContent>So the exercise coach never suggests a move that could hurt you.</AccordionContent>
            </AccordionItem>
            <AccordionItem value="data">
              <AccordionTrigger>Who sees my data?</AccordionTrigger>
              <AccordionContent>Only you.</AccordionContent>
            </AccordionItem>
          </Accordion>
          <Row>
            <Avatar>
              <AvatarFallback>AK</AvatarFallback>
            </Avatar>
            <Separator orientation="vertical" className="h-8" />
            <ScrollArea className="h-24 w-56 rounded-lg border p-3 text-sm">
              {FOODS.concat(FOODS).map((f, i) => (
                <div key={i}>{f}</div>
              ))}
            </ScrollArea>
          </Row>
        </Section>
      </main>
    </div>
  )
}

/** The theme's chip (app/theme.css `chip`): pickers, then a display chip of what was picked. */
function Chips() {
  const [picked, setPicked] = useState(['Vegetarian'])
  const toggle = (name) => setPicked((prev) => (prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name]))
  return (
    <div className="flex flex-col gap-2">
      <div role="group" aria-label="Diet" className="flex flex-wrap gap-2">
        {['Vegetarian', 'Vegan', 'Jain', 'Halal'].map((name) => (
          <label key={name} className="chip">
            <input type="checkbox" className="sr-only" checked={picked.includes(name)} onChange={() => toggle(name)} />
            {picked.includes(name) && <Check aria-hidden="true" />}
            {name}
          </label>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <span className="chip" data-picked=""><Check aria-hidden="true" />Peanut</span>
      </div>
    </div>
  )
}
