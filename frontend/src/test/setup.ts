/**
 * Minimal in-memory `localStorage` for tests.
 *
 * Node 25+ ships its own `localStorage` global that is undefined unless started
 * with a flag, and it shadows the one jsdom would provide. The code under test
 * only needs get/set/remove/clear, so a plain Map-backed store is enough and
 * keeps the tests independent of the Node version and of a DOM environment.
 */
class MemoryStorage implements Storage {
  private data = new Map<string, string>()

  get length(): number {
    return this.data.size
  }
  clear(): void {
    this.data.clear()
  }
  getItem(key: string): string | null {
    return this.data.has(key) ? (this.data.get(key) as string) : null
  }
  key(index: number): string | null {
    return Array.from(this.data.keys())[index] ?? null
  }
  removeItem(key: string): void {
    this.data.delete(key)
  }
  setItem(key: string, value: string): void {
    this.data.set(key, String(value))
  }
}

Object.defineProperty(globalThis, 'localStorage', {
  value: new MemoryStorage(),
  configurable: true,
  writable: true
})
