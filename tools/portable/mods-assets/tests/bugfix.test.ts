import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On, ToolCallArgs } from 'claude-code'

const A = 'a'.repeat(64)
const B = 'b'.repeat(64)
const C = 'c'.repeat(64)
const ROOT = '/work/repo'
const RECIPE = { repro: ['python3', 'repro.py'], expectedExit: 1, contains: 'BUG reproduced', verify: [['python3', 'tests.py']], timeoutMs: 1000 }
const TOOL = 'mcp__pstack-mods__bugfix'
type Role = 'correctness' | 'quality'
type ProcessResult = { exitCode: number; stdout: string; stderr: string; isStdoutTruncated?: boolean; isStderrTruncated?: boolean }
type Receipt = { snapshot: string; argv: string[]; exitCode: number }
type Status = { stage: string; snapshot: string | null; missing: string[]; failure: string | null; pending: string[]; evidence: { reproduction: Receipt | null; verification: { snapshot: string; runs: Receipt[] } | null; reviews: Partial<Record<Role, { snapshot: string; agentId: string; summary: string }>> } }
type Child = { id: string; role: Role; prompt: string; reads: string[] }

function transport(result: ProcessResult) {
  return { isStdoutTruncated: false, isStderrTruncated: false, ...result }
}
function jsonResult(value: unknown): ProcessResult {
  return { exitCode: 0, stdout: JSON.stringify(value), stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
}
function parse(text: unknown): Status {
  expect(typeof text).toBe('string')
  return JSON.parse(String(text).trim().split('\n').pop()!)
}
function notVerified(value: Status): void {
  expect(value.stage).not.toBe('verified')
  expect(value.missing.length > 0).toBe(true)
}

function harness(on: On) {
  const clock = mock.clock(on)
  const h = {
    clock, snapshot: A, clean: true, helper: '', sessionId: 'test-session',
    saved: new Map<string, unknown>(), statuses: [] as string[],
    runCalls: [] as string[][], helperCalls: [] as string[][], childCalls: [] as string[],
    children: [] as Child[], fsReads: [] as string[],
    spawnFailure: '' as '' | 'deny' | 'missing-id' | 'duplicate-id',
    identityFailure: '' as '' | 'wrong-type' | 'wrong-owner' | 'nested' | 'missing',
    readMode: 'complete' as 'complete' | 'partial' | 'token-truncated' | 'error' | 'deny',
    rubricFailure: false,
    beforeSpawnReturn: undefined as undefined | ((id: string) => Promise<void>),
    beforeRubricRead: undefined as undefined | (() => Promise<void>),
    beforeAgentList: undefined as undefined | (() => Promise<void>),
    snapshotReply: undefined as undefined | (() => ProcessResult | Promise<ProcessResult>),
    runReply: undefined as undefined | ((command: string[]) => ProcessResult | Promise<ProcessResult>),
    diffReply: undefined as undefined | (() => ProcessResult | Promise<ProcessResult>),
  }
  on('session.start', () => ({ cwd: ROOT }))
  on('session.id', () => ({ value: h.sessionId }))
  on('session.cwd', () => ({ value: ROOT }))
  on('session.end', ($, e) => ({ sessionId: e.sessionId }))
  on('classic.SessionStart', () => ({}))
  on('classic.Stop', () => ({}))
  on('turn.complete', () => ({ text: '' }))
  on('command.register', () => ({ value: { command: 'pstack-bugfix' } }))
  on('tool.register', () => ({ value: { tool: TOOL } }))
  on('agent.register', () => ({ value: { agent: 'pstack-mods:bugfix-reviewer' } }))
  on('store.get', ($, e) => ({ value: h.saved.get(e.key) }))
  on('store.set', ($, e) => { h.saved.set(e.key, e.value); return { value: undefined } })
  on('store.delete', ($, e) => { h.saved.delete(e.key); return { value: undefined } })
  on('ui.status', ($, e) => { h.statuses.push(e.text ?? ''); return { value: undefined } })
  on('ui.render', () => ({ type: 'Text', props: {}, children: ['host prompt'] }))
  on('fs.read', async ($, e) => {
    h.fsReads.push(e.path)
    if (h.beforeRubricRead) await h.beforeRubricRead()
    return h.rubricFailure ? { deny: 'Required rubric unavailable' } : { value: '# Full pinned rubric\nReview every requirement.' }
  })
  on('process.run', async ($, e) => {
    h.helperCalls.push([...e.argv])
    h.helper = e.argv[1]!
    expect(e.argv[0]).toBe('python3')
    expect(e.argv[1]).toMatch(/\/hooks\/evidence\.py$/)
    if (e.argv[2] === 'snapshot') {
      return { value: transport(h.snapshotReply ? await h.snapshotReply() : jsonResult({ schema: 1, digest: h.snapshot, root: ROOT, head: 'f'.repeat(40), files: 3, clean: h.clean })) }
    }
    if (e.argv[2] === 'diff') {
      return { value: transport(h.diffReply ? await h.diffReply() : jsonResult({ schema: 1, diff: 'diff --git a/repro.py b/repro.py\n-old\n+fixed', files: [ROOT + '/repro.py'], untracked: [] })) }
    }
    expect(e.argv[2]).toBe('run')
    expect(e.argv[3]).toBe(ROOT)
    const request = JSON.parse(e.argv[4]!)
    expect(request.timeoutMs).toBe(RECIPE.timeoutMs)
    h.runCalls.push(request.argv)
    if (h.runReply) return { value: transport(await h.runReply(request.argv)) }
    return { value: transport(processEvidence(request.argv, h.snapshot === A ? 1 : 0, h.snapshot === A ? 'BUG reproduced' : 'passed')) }
  })
  on('agent.spawn', async ($, e) => {
    if (h.spawnFailure === 'deny') return { deny: 'No reviewer capacity' }
    if (h.spawnFailure === 'missing-id') return { model: 'claude-test' }
    const id = h.spawnFailure === 'duplicate-id' ? 'reviewer-1' : 'reviewer-' + (h.children.length + 1)
    const role = e.description.endsWith('correctness') ? 'correctness' : 'quality'
    const paths = JSON.parse(e.prompt.match(/First Read both files in full: (\[[^\n]+?\])/s)![1]!)
    h.children.push({ id, role, prompt: e.prompt, reads: paths })
    if (h.beforeSpawnReturn) await h.beforeSpawnReturn(id)
    // Claude 2.1.289's native test dispatcher feeds this event stub straight to
    // the plugin API adapter. That adapter reads the internal Agent-tool result
    // envelope before returning public {model, agentId}; supply both shapes.
    // Only identity is provided here. Final text arrives through turn.complete.
    return { model: 'claude-test', agentId: id, result: { agentId: id, resolvedModel: 'claude-test' } }
  })
  on('agent.list', async () => {
    if (h.beforeAgentList) await h.beforeAgentList()
    return { value: h.identityFailure === 'missing' ? [] : h.children.map(child => ({
    id: child.id, description: 'Bug fix ' + child.role, status: 'running',
    type: h.identityFailure === 'wrong-type' ? 'general-purpose' : 'pstack-mods:bugfix-reviewer',
    spawnedBy: h.identityFailure === 'wrong-owner' ? 'another-plugin' : 'pstack-mods',
    ...(h.identityFailure === 'nested' ? { parentId: 'another-child' } : {}),
  })) }
  })
  on('tool.call', ($, e) => {
    h.childCalls.push(e.tool)
    if (e.tool !== 'Read') return { result: 'host accepted' }
    if (h.readMode === 'deny') return { deny: 'Read denied' }
    if (h.readMode === 'error') return { isError: true, result: 'Read failed' }
    return { result: { type: 'text', file: { filePath: e.file_path, content: 'Full source\n', startLine: 1,
      numLines: h.readMode === 'partial' ? 1 : 8, totalLines: 8, truncatedByTokenCap: h.readMode === 'token-truncated' } } }
  })
  return h
}
type Harness = ReturnType<typeof harness>
function processEvidence(argv: string[], exitCode: number, stdout = '', extra: Record<string, unknown> = {}): ProcessResult {
  return jsonResult({ schema: 1, argv, exitCode, timedOut: false, stdout, stderr: '', stdoutTruncated: false, stderrTruncated: false, ...extra })
}
async function start($: Engine): Promise<Status> {
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: ROOT })
  return command($, 'start ' + JSON.stringify(RECIPE))
}
async function command($: Engine, args: string): Promise<Status> {
  const value = await $.command.run({ command: 'pstack-bugfix', args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 80 } })
  return parse(value.text)
}
async function action($: Engine, action: string): Promise<Status> {
  return parse((await $.tool.call({ tool: TOOL, action })).result)
}
async function verifiedTests($: Engine, h: Harness): Promise<Status> {
  await start($)
  expect((await action($, 'reproduce')).stage).toBe('fix')
  h.snapshot = B
  h.clean = false
  const value = await action($, 'verify')
  expect(value.stage).toBe('independent review')
  expect(value.missing).toEqual(['correctness review', 'quality review'])
  return value
}
function report(child: Child, extra: Record<string, unknown> = {}): string {
  return JSON.stringify({ schema: 1, snapshot: B, role: child.role, verdict: 'clean', summary: 'Reviewed complete rubric, implementation, tests, and callers.', findings: [], ...extra })
}
// The native test engine accepts host event metadata. Put it on a typed
// variable because production $.tool.call's overload omits the host-only axis.
async function childTool($: Engine, input: ToolCallArgs & { agentId: string }) {
  return $.tool.call(input)
}
async function readChild($: Engine, child: Child, paths = [...child.reads, ROOT + '/repro.py']): Promise<void> {
  for (const file_path of paths) await childTool($, { tool: 'Read', agentId: child.id, file_path })
}
async function finishChild($: Engine, child: Child, answer = report(child), extra: Record<string, unknown> = {}): Promise<void> {
  await $.turn.complete({ turnId: 'turn-' + child.id, agentId: child.id, answer, durationMs: 30, isAborted: false, reason: 'answer', ...extra } as Parameters<Engine['turn']['complete']>[0])
}
async function complete($: Engine, h: Harness): Promise<Status> {
  await verifiedTests($, h)
  await action($, 'review')
  for (const child of h.children) { await readChild($, child); await finishChild($, child) }
  const value = await action($, 'status')
  expect(value.stage, 'complete lifecycle fixture must reach verified').toBe('verified')
  return value
}

test('pipeline is off until direct opt-in; edits and Stop are unaffected', async ($, on) => {
  const h = harness(on)
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: ROOT })
  const value = await action($, 'status')
  expect(value.stage).toBe('off')
  expect((await $.tool.call({ tool: 'Edit', file_path: ROOT + '/repro.py', old_string: 'x', new_string: 'y' })).result).toBe('host accepted')
  expect((await $.classic.Stop({ stop_hook_active: false })).block).toBeUndefined()
  expect((await $.tool.call({ tool: TOOL, action: 'reproduce' })).deny).toMatch(/Start or resume/)
  expect(h.helperCalls).toEqual([])
})

test('start blocks editing until an observed reproduction; model claims are not evidence', async ($, on) => {
  const h = harness(on)
  const value = await start($)
  expect(value.stage).toBe('repro')
  expect(value.missing).toContain('observed failing reproduction')
  expect((await $.tool.call({ tool: 'Edit', file_path: ROOT + '/repro.py', old_string: 'x', new_string: 'y' })).deny).toMatch(/observe the failing reproduction/)
  await $.turn.complete({ turnId: 'parent', answer: 'Tests and both reviews passed. Complete.', durationMs: 1, isAborted: false, reason: 'answer' })
  notVerified(await action($, 'status'))
  expect(h.runCalls).toEqual([])
})

for (const requested of ['verify', 'review']) {
  test(requested + ' without prerequisites blocks with visible missing evidence', async ($, on) => {
    const h = harness(on)
    await start($)
    const value = await action($, requested)
    expect(value.stage).toBe('blocked')
    expect(value.failure).toMatch(/Missing/)
    expect(value.evidence.reproduction).toBe(null)
    notVerified(value)
    expect(h.children).toEqual([])
  })
}

for (const [name, exitCode, output] of [['passes unexpectedly', 0, 'BUG reproduced'], ['wrong exit', 2, 'BUG reproduced'], ['wrong failure', 1, 'unrelated error']] as const) {
  test('reproduction ' + name + ' cannot count', async ($, on) => {
    const h = harness(on)
    h.runReply = argv => processEvidence(argv, exitCode, output)
    await start($)
    const value = await action($, 'reproduce')
    expect(value.stage).toBe('blocked')
    expect(value.failure).toMatch(/did not show the configured failure/)
    expect(value.evidence.reproduction).toBe(null)
    notVerified(value)
  })
}

for (const [name, result, message] of [
  ['helper exits nonzero', { exitCode: 1, stdout: '', stderr: 'missing executable' }, /Test process unavailable/],
  ['helper JSON malformed', { exitCode: 0, stdout: '{bad', stderr: '' }, /SyntaxError/],
  ['helper transport truncated', { exitCode: 0, stdout: '{}', stderr: '', isStdoutTruncated: true }, /Test process unavailable/],
  ['helper evidence malformed', jsonResult({ schema: 1, argv: ['wrong'] }), /Malformed process evidence/],
  ['process timed out', processEvidence(RECIPE.repro, -9, '', { timedOut: true }), /timed out/],
] as const) {
  test(name + ' cannot produce reproduction evidence', async ($, on) => {
    const h = harness(on)
    h.runReply = () => result
    await start($)
    const value = await action($, 'reproduce')
    expect(value.stage).toBe('blocked')
    expect(value.failure).toMatch(message)
    expect(value.evidence.reproduction).toBe(null)
    notVerified(value)
  })
}

test('reproduction must remain on one snapshot', async ($, on) => {
  const h = harness(on)
  await start($)
  h.runReply = argv => { h.snapshot = B; return processEvidence(argv, 1, 'BUG reproduced') }
  const value = await action($, 'reproduce')
  expect(value.stage).toBe('blocked')
  expect(value.failure).toMatch(/changed the code snapshot/)
  expect(value.evidence.reproduction).toBe(null)
})

test('verification requires a changed snapshot and all commands to pass', async ($, on) => {
  const h = harness(on)
  await start($)
  await action($, 'reproduce')
  let value = await action($, 'verify')
  expect(value.stage).toBe('blocked')
  expect(value.failure).toMatch(/Missing changed snapshot/)
  h.snapshot = B
  await command($, 'resume')
  h.runReply = argv => processEvidence(argv, argv[1] === 'tests.py' ? 1 : 0, 'one assertion fails')
  value = await action($, 'verify')
  expect(value.stage).toBe('blocked')
  expect(value.failure).toMatch(/Verification failed/)
  expect(value.evidence.verification).toBe(null)
  expect(value.missing).toContain('passing reproduction and verification')
})

test('code changing during verification discards all passing results', async ($, on) => {
  const h = harness(on)
  await start($)
  await action($, 'reproduce')
  h.snapshot = B
  h.runReply = argv => { h.snapshot = C; return processEvidence(argv, 0, 'passed') }
  const value = await action($, 'verify')
  expect(value.stage).toBe('blocked')
  expect(value.failure).toMatch(/Code changed during verification/)
  expect(value.evidence.verification).toBe(null)
  notVerified(value)
})

test('complete lifecycle requires two fresh reviewers and callback-observed full Reads', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  let value = await action($, 'review')
  expect(value.stage).toBe('independent review')
  expect(value.pending).toEqual(['correctness', 'quality'])
  expect(h.children.map(c => c.id)).toEqual(['reviewer-1', 'reviewer-2'])
  expect(h.fsReads.length).toBe(4)
  expect(h.children[0]!.reads).not.toEqual(h.children[1]!.reads)
  await finishChild($, { ...h.children[0]!, id: 'impostor' })
  expect((await action($, 'status')).evidence.reviews).toEqual({})
  const first = h.children[0]!
  await readChild($, first)
  await finishChild($, first)
  value = await action($, 'status')
  expect(value.stage).toBe('independent review')
  expect(value.missing).toEqual(['quality review'])
  expect(value.evidence.reviews.correctness?.agentId).toBe(first.id)
  const second = h.children[1]!
  await readChild($, second)
  await finishChild($, second)
  value = await action($, 'status')
  expect(value.stage).toBe('verified')
  expect(value.missing).toEqual([])
  expect(value.failure).toBe(null)
  expect(value.evidence.verification?.snapshot).toBe(B)
  expect(value.evidence.verification?.runs.map(r => r.argv)).toEqual([RECIPE.repro, ...RECIPE.verify])
  expect(value.evidence.reviews.quality?.agentId).toBe(second.id)
  expect((await $.classic.Stop({ stop_hook_active: false })).block).toBeUndefined()
})

test('repeated start and actions preserve evidence and never duplicate processes or reviewers', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  await command($, 'start ' + JSON.stringify(RECIPE))
  await action($, 'reproduce')
  await action($, 'verify')
  await action($, 'review')
  await action($, 'review')
  expect(h.runCalls).toEqual([RECIPE.repro, RECIPE.repro, ...RECIPE.verify])
  expect(h.children.length).toBe(2)
  for (const child of h.children) { await readChild($, child); await finishChild($, child) }
  await action($, 'review')
  const value = await command($, 'start ' + JSON.stringify(RECIPE))
  expect(value.stage).toBe('verified')
  expect(value.missing).toEqual([])
  expect(h.children.length).toBe(2)
  expect(h.runCalls.length).toBe(3)
})

test('changed snapshots invalidate both verification and accepted reviews', async ($, on) => {
  const h = harness(on)
  expect((await complete($, h)).stage).toBe('verified')
  h.snapshot = C
  const value = await action($, 'status')
  expect(value.stage).toBe('verification')
  expect(value.snapshot).toBe(C)
  expect(value.evidence.verification).toBe(null)
  expect(value.evidence.reviews).toEqual({})
  expect(value.failure).toMatch(/snapshot changed/)
  expect(value.missing).toEqual(['passing reproduction and verification', 'correctness review', 'quality review'])
})

test('background snapshot polling invalidates a previously verified state', async ($, on) => {
  const h = harness(on)
  await complete($, h)
  h.snapshot = C
  await h.clock.advance(5000)
  expect(h.statuses[h.statuses.length - 1]).toMatch(/Bug fix: verification/)
  expect(h.statuses[h.statuses.length - 1]).toMatch(/snapshot changed/)
  notVerified(await action($, 'status'))
})

for (const failure of ['deny', 'missing-id', 'duplicate-id'] as const) {
  test('spawn ' + failure + ' blocks instead of accepting claimed review text', async ($, on) => {
    const h = harness(on)
    h.spawnFailure = failure
    await verifiedTests($, h)
    const value = await action($, 'review')
    expect(value.stage).toBe('blocked')
    expect(value.failure).toMatch(/fresh identity/)
    expect(value.pending).toEqual([])
    expect(value.evidence.reviews).toEqual({})
    notVerified(value)
  })
}
for (const failure of ['wrong-type', 'wrong-owner', 'nested', 'missing'] as const) {
  test('reviewer identity ' + failure + ' is rejected', async ($, on) => {
    const h = harness(on)
    h.identityFailure = failure
    await verifiedTests($, h)
    const value = await action($, 'review')
    expect(value.stage).toBe('blocked')
    expect(value.failure).toMatch(/identity could not be verified/)
    expect(value.evidence.reviews).toEqual({})
    notVerified(value)
  })
}

for (const mode of ['partial', 'token-truncated', 'error', 'deny'] as const) {
  test('reviewer ' + mode + ' Reads never satisfy mandatory rubric coverage', async ($, on) => {
    const h = harness(on)
    await verifiedTests($, h)
    await action($, 'review')
    h.readMode = mode
    await readChild($, h.children[0]!)
    await finishChild($, h.children[0]!)
    const value = await action($, 'status')
    expect(value.stage).toBe('blocked')
    expect(value.failure).toMatch(/both required Thermos files in full/)
    expect(value.evidence.reviews).toEqual({})
    notVerified(value)
  })
}

test('parent preloading rubrics does not satisfy a child reviewer Read', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  await action($, 'review')
  expect(h.fsReads.length).toBe(4)
  await readChild($, h.children[0]!, [ROOT + '/repro.py'])
  await finishChild($, h.children[0]!)
  const value = await action($, 'status')
  expect(value.stage).toBe('blocked')
  expect(value.failure).toMatch(/both required Thermos files in full/)
})

test('rubric reads without an observed repository-file read are incomplete', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  await action($, 'review')
  await readChild($, h.children[0]!, h.children[0]!.reads)
  await finishChild($, h.children[0]!)
  const value = await action($, 'status')
  expect(value.stage).toBe('blocked')
  expect(value.failure).toMatch(/every changed file in full/)
})

for (const [name, extra] of [
  ['stale snapshot', { snapshot: A }], ['wrong role', { role: 'security' }], ['wrong schema', { schema: 2 }],
  ['empty coverage', { summary: '' }], ['findings', { verdict: 'findings', findings: [{ issue: 'bug remains' }] }],
  ['clean with findings', { findings: [{ issue: 'bug remains' }] }], ['incomplete', { verdict: 'incomplete' }],
] as const) {
  test('rejects reviewer report with ' + name, async ($, on) => {
    const h = harness(on)
    await verifiedTests($, h)
    await action($, 'review')
    const child = h.children[0]!
    await readChild($, child)
    await finishChild($, child, report(child, extra))
    const value = await action($, 'status')
    expect(value.stage).toBe('blocked')
    expect(value.failure).toMatch(/reviewer evidence|findings or incomplete/)
    expect(value.evidence.reviews).toEqual({})
    notVerified(value)
  })
}
for (const [name, answer, extra] of [
  ['missing final text', '', {}], ['malformed JSON', 'looks clean to me', {}],
  ['failed turn', '', { reason: 'error' }], ['interrupted turn', '', { reason: 'aborted', isAborted: true }],
] as const) {
  test('rejects reviewer ' + name, async ($, on) => {
    const h = harness(on)
    await verifiedTests($, h)
    await action($, 'review')
    await readChild($, h.children[0]!)
    await finishChild($, h.children[0]!, answer, extra)
    const value = await action($, 'status')
    expect(value.stage).toBe('blocked')
    expect(value.failure).toMatch(/no result|SyntaxError/)
    expect(value.evidence.reviews).toEqual({})
    notVerified(value)
  })
}

test('missing reviewer completion times out, clears pending work, and rejects late answers', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  await action($, 'review')
  for (const child of h.children) await readChild($, child)
  await h.clock.advance(300000)
  let value = await action($, 'status')
  expect(value.stage).toBe('blocked')
  expect(value.failure).toMatch(/timed out or returned no final result/)
  expect(value.pending).toEqual([])
  for (const child of h.children) await finishChild($, child)
  value = await action($, 'status')
  expect(value.evidence.reviews).toEqual({})
  notVerified(value)
})

test('code changing between reviewer start and callback invalidates the report', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  await action($, 'review')
  await readChild($, h.children[0]!)
  h.snapshot = C
  await finishChild($, h.children[0]!)
  const value = await action($, 'status')
  expect(value.stage).toBe('blocked')
  expect(value.failure).toMatch(/Code changed during independent review/)
  expect(value.evidence.reviews).toEqual({})
})

test('independent child guard denies edits, commands, spawning, and pipeline invocation', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  await action($, 'review')
  const attempts = [
    { tool: 'Bash', command: 'touch bad' },
    { tool: 'Edit', file_path: ROOT + '/repro.py', old_string: 'x', new_string: 'y' },
    { tool: 'Write', file_path: ROOT + '/repro.py', content: 'bad' },
    { tool: 'Agent', description: 'Nested agent', prompt: 'Do more work' },
    { tool: TOOL, action: 'status' },
  ] as const
  for (const input of attempts) {
    const value = await childTool($, { ...input, agentId: h.children[0]!.id })
    expect(value.deny).toMatch(/read-only/)
  }
  expect(h.childCalls).toEqual([])
  notVerified(await action($, 'status'))
})

// A child skips the exact spawning callback, not every hook owned by that mod.
// Drive the actual host dispatch rather than calling the guard function directly.
test('native callback skipping leaves a separate same-plugin guard active', { plugins: [{
  name: 'callback-boundary-regression',
  register(on) {
    on('tool.call', async ($, e, next) => e.tool === 'Bash' ? { deny: 'independent guard saw nested call' } : next(e))
    on('tool.call', { tool: 'mcp__callback-boundary-regression__runner' }, async $ => {
      const result = await $.tool.call({ tool: 'Bash', command: 'echo must-not-run' })
      return { result: JSON.stringify(result) }
    })
  },
}] }, async ($, on) => {
  harness(on)
  const value = await $.tool.call({ tool: 'mcp__callback-boundary-regression__runner' })
  expect(value.result).toBe('{"deny":"independent guard saw nested call"}')
})

test('Stop gives one reminder and then pauses without a retry loop', async ($, on) => {
  harness(on)
  await start($)
  const first = await $.classic.Stop({ stop_hook_active: false })
  expect(first.block).toMatch(/not verified/)
  expect(first.block).toMatch(/observed failing reproduction/)
  expect((await $.classic.Stop({ stop_hook_active: false })).block).toBeUndefined()
  const value = await action($, 'status')
  expect(value.stage).toBe('paused')
  expect(value.failure).toMatch(/one reminder/)
  expect((await $.classic.Stop({ stop_hook_active: false })).block).toBeUndefined()
})

test('Stop active retry flag pauses immediately and child Stop never consumes parent retry', async ($, on) => {
  harness(on)
  await start($)
  expect((await $.classic.Stop({ stop_hook_active: false, agent_id: 'child' })).block).toBeUndefined()
  expect((await action($, 'status')).stage).toBe('repro')
  expect((await $.classic.Stop({ stop_hook_active: false })).block).toMatch(/not verified/)
  expect((await $.classic.Stop({ stop_hook_active: true })).block).toBeUndefined()
  expect((await action($, 'status')).stage).toBe('paused')
})

test('Stop yields while reviewers are pending without claiming verification', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  await action($, 'review')
  expect((await $.classic.Stop({ stop_hook_active: false })).block).toBeUndefined()
  const value = await action($, 'status')
  expect(value.stage).toBe('independent review')
  expect(value.pending).toEqual(['correctness', 'quality'])
  notVerified(value)
})

test('parent interruption invalidates reviews and resume demands fresh verification', async ($, on) => {
  const h = harness(on)
  await complete($, h)
  await $.turn.complete({ turnId: 'parent', answer: '', durationMs: 1, isAborted: true, reason: 'aborted' })
  let value = await action($, 'status')
  expect(value.stage).toBe('paused')
  expect(value.evidence.reproduction?.snapshot).toBe(A)
  expect(value.evidence.verification).toBe(null)
  expect(value.evidence.reviews).toEqual({})
  value = await command($, 'resume')
  expect(value.stage).toBe('verification')
  expect(value.missing).toContain('passing reproduction and verification')
})

test('pause discards pending callbacks, repeated start does not secretly resume, cancel clears marker', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  await action($, 'review')
  for (const child of h.children) await readChild($, child)
  expect((await command($, 'pause')).stage).toBe('paused')
  expect((await command($, 'start ' + JSON.stringify(RECIPE))).stage).toBe('paused')
  for (const child of h.children) await finishChild($, child)
  let value = await action($, 'status')
  expect(value.evidence.reviews).toEqual({})
  expect(value.pending).toEqual([])
  value = await command($, 'cancel')
  expect(value.stage).toBe('off')
  expect(h.saved.size).toBe(0)
  expect((await $.tool.call({ tool: 'Write', file_path: ROOT + '/repro.py', content: 'x' })).result).toBe('host accepted')
})

for (const boundary of ['reload', 'clear', 'resume'] as const) {
  test(boundary + ' retains only an untrusted reminder and restores no evidence', async ($, on) => {
    const h = harness(on)
    await complete($, h)
    h.saved.set('bugfix:test-session', { active: true, stage: 'verified', snapshot: B, recipe: RECIPE, repro: { snapshot: A }, reviews: { correctness: 'clean', quality: 'clean' } })
    if (boundary === 'reload') await $.session.start({ surface: 'terminal', isInteractive: true, cwd: ROOT })
    else await $.classic.SessionStart({ source: boundary })
    let value = await action($, 'status')
    expect(value.stage).toBe('paused')
    expect(value.failure).toMatch(/no evidence was restored/)
    expect(value.evidence.reproduction).toBe(null)
    expect(value.evidence.verification).toBe(null)
    expect(value.evidence.reviews).toEqual({})
    expect(value.missing).toContain('configured recipe')
    value = await command($, 'resume')
    notVerified(value)
    expect(value.evidence.reproduction).toBe(null)
    h.snapshot = A
    expect((await command($, 'start ' + JSON.stringify(RECIPE))).stage).toBe('repro')
  })
}

test('fresh clear session has no inherited pipeline or old session marker', async ($, on) => {
  const h = harness(on)
  await complete($, h)
  h.sessionId = 'new-session-after-clear'
  await $.classic.SessionStart({ source: 'clear' })
  const value = await action($, 'status')
  expect(value.stage).toBe('off')
  expect(value.evidence.reproduction).toBe(null)
  expect(value.evidence.verification).toBe(null)
  expect(value.evidence.reviews).toEqual({})
})

const BAND = { plugin: 'pstack-mods', component: 'AbovePrompt', requestId: 'bugfix-band', viewport: { columns: 80, rows: 30 },
  props: { hasSurvey: false, isWorking: false, maxRows: 15, bodyColumns: 75, scroll: { offset: 0, bodyRows: 15 }, view: {} } } as const
for (const surface of ['terminal', 'desktop'] as const) {
  test(surface + ' renders stages and missing evidence, including honest blocked status', async ($, on) => {
    harness(on)
    await $.session.start({ surface, isInteractive: true, cwd: ROOT })
    const ui = await $.ui.mount({ ...BAND, surface })
    expect(await ui.find({ type: 'Text', text: 'host prompt' }), 'off state yields to host prompt').toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Bug fix:/ })).toBeUndefined()
    await command($, 'start ' + JSON.stringify(RECIPE))
    expect(await ui.find({ type: 'Text', text: /Bug fix: repro/ }), 'active stage rendered').toBeDefined()
    expect(await ui.find({ type: 'Text', text: /observed failing reproduction/ })).toBeDefined()
    await action($, 'verify')
    expect(await ui.find({ type: 'Text', text: /Bug fix: blocked/ }), 'blocked stage rendered').toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Missing observed failing reproduction/ })).toBeDefined()
    await ui.unmount()
  })
}

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>(done => { resolve = done })
  return { promise, resolve }
}

test('an interrupted in-flight process cannot create evidence when its result arrives', async ($, on) => {
  const h = harness(on)
  const entered = deferred()
  const released = deferred()
  await start($)
  h.runReply = async argv => { entered.resolve(); await released.promise; return processEvidence(argv, 1, 'BUG reproduced') }
  const running = action($, 'reproduce')
  await entered.promise
  let value = await command($, 'pause')
  expect(value.stage).toBe('paused')
  expect((await $.tool.call({ tool: TOOL, action: 'reproduce' })).deny).toMatch(/Start or resume/)
  value = await command($, 'resume')
  expect(value.stage).toBe('paused')
  released.resolve()
  value = await running
  expect(value.stage).toBe('paused')
  expect(value.evidence.reproduction).toBe(null)
  notVerified(value)
})

test('parent abort during verification discards late process success', async ($, on) => {
  const h = harness(on)
  const entered = deferred()
  const released = deferred()
  await start($)
  await action($, 'reproduce')
  h.snapshot = B
  h.runReply = async argv => { entered.resolve(); await released.promise; return processEvidence(argv, 0, 'passed') }
  const running = action($, 'verify')
  await entered.promise
  expect((await $.tool.call({ tool: TOOL, action: 'verify' })).deny).toMatch(/already running/)
  expect((await $.classic.Stop({ stop_hook_active: false })).block).toBeUndefined()
  await $.turn.complete({ turnId: 'parent', answer: '', durationMs: 1, isAborted: true, reason: 'aborted' })
  released.resolve()
  const value = await running
  expect(value.stage).toBe('paused')
  expect(value.evidence.verification).toBe(null)
  expect(value.evidence.reviews).toEqual({})
  notVerified(value)
})

test('reviewer tools before spawn registration and after pause stay guarded', async ($, on) => {
  const h = harness(on)
  const early: unknown[] = []
  h.beforeSpawnReturn = async id => {
    early.push((await childTool($, { tool: 'Bash', agentId: id, command: 'touch unsafe' })).deny)
  }
  await verifiedTests($, h)
  expect((await action($, 'review')).stage).toBe('independent review')
  expect(early.length).toBe(2)
  for (const deny of early) expect(deny).toMatch(/initializing|stale/)
  expect(h.childCalls).toEqual([])
  await command($, 'pause')
  expect((await childTool($, { tool: 'Write', agentId: h.children[0]!.id, file_path: ROOT + '/repro.py', content: 'unsafe' })).deny).toMatch(/initializing|stale/)
  notVerified(await action($, 'status'))
})

test('every changed file must be read; reading a different repository file does not count', async ($, on) => {
  const h = harness(on)
  h.diffReply = () => jsonResult({ schema: 1, diff: 'two changed files', files: [ROOT + '/repro.py', ROOT + '/caller.py'], untracked: [] })
  await verifiedTests($, h)
  await action($, 'review')
  const child = h.children[0]!
  await readChild($, child, [...child.reads, ROOT + '/repro.py', ROOT + '/unrelated.py'])
  await finishChild($, child)
  const value = await action($, 'status')
  expect(value.stage).toBe('blocked')
  expect(value.failure).toMatch(/every changed file in full/)
  expect(value.evidence.reviews).toEqual({})
})

test('complete rubrics plus partial changed-file Read cannot produce an accepted review', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  await action($, 'review')
  const child = h.children[0]!
  await readChild($, child, child.reads)
  h.readMode = 'partial'
  await readChild($, child, [ROOT + '/repro.py'])
  await finishChild($, child)
  const value = await action($, 'status')
  expect(value.stage).toBe('blocked')
  expect(value.failure).toMatch(/every changed file in full/)
  notVerified(value)
})

test('missing local pinned rubric blocks before any reviewer is spawned', async ($, on) => {
  const h = harness(on)
  h.rubricFailure = true
  await verifiedTests($, h)
  const value = await action($, 'review')
  expect(value.stage).toBe('blocked')
  expect(value.failure).toMatch(/Required rubric unavailable/)
  expect(h.children).toEqual([])
  notVerified(value)
})

for (const [name, reply, message] of [
  ['failed helper', { exitCode: 1, stdout: '', stderr: 'diff failed' }, /Review diff unavailable/],
  ['truncated helper', { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: true }, /Review diff unavailable/],
  ['missing file list', jsonResult({ schema: 1, diff: '', untracked: [] }), /Invalid review file scope/],
  ['file outside repository', jsonResult({ schema: 1, diff: '', files: ['/elsewhere/file.py'], untracked: [] }), /Invalid review file scope/],
] as const) {
  test('review diff ' + name + ' cannot start independent review', async ($, on) => {
    const h = harness(on)
    h.diffReply = () => reply
    await verifiedTests($, h)
    const value = await action($, 'review')
    expect(value.stage).toBe('blocked')
    expect(value.failure).toMatch(message)
    expect(h.children).toEqual([])
    notVerified(value)
  })
}

test('session end invalidates live evidence and never reports verified afterward', async ($, on) => {
  const h = harness(on)
  expect((await complete($, h)).stage).toBe('verified')
  await $.session.end({ reason: 'other', sessionId: h.sessionId, resume: { id: h.sessionId } })
  const value = await action($, 'status')
  expect(value.stage).toBe('paused')
  expect(value.failure).toMatch(/Session ended/)
  expect(value.evidence.verification).toBe(null)
  expect(value.evidence.reviews).toEqual({})
  notVerified(value)
})

test('direct status never preserves verified after snapshot failure', async ($, on) => {
  const h = harness(on)
  expect((await complete($, h)).stage).toBe('verified')
  h.snapshotReply = () => ({ exitCode: 1, stdout: '', stderr: 'unsupported symlink' })
  const value = await command($, 'status')
  expect(value.stage).toBe('blocked')
  expect(value.evidence.verification).toBe(null)
})

test('empty HEAD diff cannot satisfy repository review', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  h.diffReply = () => jsonResult({schema:1, diff:'', files:[], untracked:[]})
  await action($, 'review')
  for (const child of h.children) { await readChild($, child, child.reads); await finishChild($, child) }
  expect((await action($, 'status')).stage).not.toBe('verified')
})


test('cancel during reviewer snapshot stays off', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  await action($, 'review')
  const child = h.children[0]!
  await readChild($, child)
  let signalEntered!: () => void
  let release!: () => void
  const entered = new Promise<void>(resolve => { signalEntered = resolve })
  const wait = new Promise<void>(resolve => { release = resolve })
  h.snapshotReply = async () => {
    signalEntered()
    await wait
    return jsonResult({schema:1,digest:B,root:ROOT,head:'f'.repeat(40),files:3,clean:false})
  }
  const completion = finishChild($, child)
  await entered
  expect((await command($, 'cancel')).stage).toBe('off')
  release()
  await completion
  expect((await action($, 'status')).stage).toBe('off')
})

test('dirty baseline cannot mint a reproduction receipt against an incomplete HEAD diff', async ($, on) => {
  const h = harness(on)
  h.clean = false
  await start($)
  const value = await action($, 'reproduce')
  expect(value.stage).toBe('blocked')
  expect(value.failure).toMatch(/clean|commit/i)
  expect(value.evidence.reproduction).toBe(null)
  expect(h.runCalls).toEqual([])
  notVerified(value)
})

test('version-pinned native spawn fixture maps Agent result envelope to callback identity', { plugins: [{
  name: 'spawn-envelope-fixture',
  register(on) {
    on('tool.call', { tool: 'mcp__spawn-envelope-fixture__run' }, async $ => ({
      result: JSON.stringify(await $.agent.spawn({ prompt: 'Fixture only. No model is called.' })),
    }))
  },
}] }, async ($, on) => {
  // Undocumented 2.1.289 test-adapter compatibility. This represents a core
  // identity answer; it does not establish that any real-model child ran.
  on('agent.spawn', () => ({ model: 'claude-test', agentId: 'fixture-child',
    result: { agentId: 'fixture-child', resolvedModel: 'claude-test' } }))
  const value = await $.tool.call({ tool: 'mcp__spawn-envelope-fixture__run' })
  expect(JSON.parse(String(value.result))).toEqual({ model: 'claude-test', agentId: 'fixture-child' })
})

test('plugin-origin command cannot opt the user into the pipeline', async ($, on) => {
  const h = harness(on)
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: ROOT })
  const value = await $.command.run({ command: 'pstack-bugfix', args: 'start ' + JSON.stringify(RECIPE),
    origin: { kind: 'plugin', name: 'other-plugin' }, presentation: { isFullscreen: false, columns: 80 } })
  expect(value.text).toMatch(/Use the command directly/)
  expect((await action($, 'status')).stage).toBe('off')
  expect(h.helperCalls).toEqual([])
})

test('deletion-only fix reviews the full diff without demanding Reads of nonexistent files', async ($, on) => {
  const h = harness(on)
  await verifiedTests($, h)
  h.diffReply = () => jsonResult({ schema: 1, diff: 'diff --git a/obsolete.py b/obsolete.py\ndeleted file mode 100644\n--- a/obsolete.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-broken()', files: [], untracked: [] })
  expect((await action($, 'review')).stage).toBe('independent review')
  for (const child of h.children) {
    expect(child.prompt).toContain('deleted file mode')
    await readChild($, child, child.reads)
    await finishChild($, child)
  }
  expect((await action($, 'status')).stage).toBe('verified')
})

test('cancel during status snapshot capture cannot repopulate the canceled snapshot', async ($, on) => {
  const h = harness(on)
  await complete($, h)
  const entered = deferred()
  const released = deferred()
  h.snapshotReply = async () => {
    entered.resolve(); await released.promise
    return jsonResult({ schema: 1, digest: C, root: ROOT, head: 'f'.repeat(40), files: 3, clean: false })
  }
  const inFlight = command($, 'status')
  await entered.promise
  expect((await command($, 'cancel')).stage).toBe('off')
  released.resolve()
  const value = await inFlight
  expect(value.stage).toBe('off')
  expect(value.snapshot).toBe(null)
  expect(value.evidence.verification).toBe(null)
  expect(value.evidence.reviews).toEqual({})
})

for (const source of ['command status', 'tool status', 'poll', 'Stop'] as const) {
test('stale ' + source + ' failure cannot block a replacement pipeline', async ($, on) => {
  const h = harness(on)
  await complete($, h)
  const entered = deferred()
  const released = deferred()
  h.snapshotReply = async () => {
    entered.resolve(); await released.promise
    return { exitCode: 1, stdout: '', stderr: 'old snapshot failed after cancellation' }
  }
  const oldStatus = source === 'command status' ? command($, 'status')
    : source === 'tool status' ? action($, 'status')
    : source === 'poll' ? h.clock.advance(5000)
    : $.classic.Stop({ stop_hook_active: false })
  await entered.promise
  await command($, 'cancel')
  h.snapshotReply = undefined
  h.snapshot = A
  h.clean = true
  expect((await command($, 'start ' + JSON.stringify(RECIPE))).stage).toBe('repro')
  released.resolve()
  await oldStatus
  const value = await action($, 'status')
  expect(value.stage).toBe('repro')
  expect(value.failure).toBe(null)
  expect(value.evidence.reproduction).toBe(null)
})

}

test('Stop awaiting an old snapshot does not spend the replacement pipeline retry', async ($, on) => {
  const h = harness(on)
  await complete($, h)
  const entered = deferred()
  const released = deferred()
  h.snapshotReply = async () => {
    entered.resolve(); await released.promise
    return jsonResult({ schema: 1, digest: B, root: ROOT, head: 'f'.repeat(40), files: 3, clean: false })
  }
  const oldStop = $.classic.Stop({ stop_hook_active: false })
  await entered.promise
  await command($, 'cancel')
  h.snapshotReply = undefined
  h.snapshot = A
  h.clean = true
  await command($, 'start ' + JSON.stringify(RECIPE))
  released.resolve()
  expect((await oldStop).block).toBeUndefined()
  expect((await $.classic.Stop({ stop_hook_active: false })).block).toMatch(/not verified/)
  expect((await action($, 'status')).stage).toBe('repro')
})

for (const boundary of ['diff', 'rubric preload', 'agent list'] as const) {
  test('cancel during review ' + boundary + ' cannot spawn or retain late reviewer work', async ($, on) => {
    const h = harness(on)
    await verifiedTests($, h)
    const entered = deferred()
    const released = deferred()
    const wait = async () => { entered.resolve(); await released.promise }
    if (boundary === 'diff') h.diffReply = async () => {
      await wait()
      return jsonResult({ schema: 1, diff: 'changed code', files: [ROOT + '/repro.py'], untracked: [] })
    }
    if (boundary === 'rubric preload') h.beforeRubricRead = wait
    if (boundary === 'agent list') h.beforeAgentList = wait
    const running = action($, 'review')
    await entered.promise
    expect((await command($, 'cancel')).stage).toBe('off')
    released.resolve()
    const value = await running
    expect(value.stage).toBe('off')
    expect(value.snapshot).toBe(null)
    expect(value.pending).toEqual([])
    expect(value.evidence.verification).toBe(null)
    expect(value.evidence.reviews).toEqual({})
    expect(h.children.length).toBe(boundary === 'agent list' ? 1 : 0)
    expect(h.saved.size).toBe(0)
    for (const child of h.children) await finishChild($, child)
    await h.clock.advance(300000)
    expect((await action($, 'status')).stage).toBe('off')
  })
}
