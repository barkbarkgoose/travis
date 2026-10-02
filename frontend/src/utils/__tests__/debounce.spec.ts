import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { debounce } from '@/utils/debounce'

describe('debounce', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('waits before calling and only fires once for rapid calls', () => {
    const fn = vi.fn()
    const debounced = debounce(fn, 100)

    debounced()
    debounced()
    debounced()
    expect(fn).not.toHaveBeenCalled()

    vi.advanceTimersByTime(100)
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('passes through the latest arguments', () => {
    const fn = vi.fn()
    const debounced = debounce(fn, 50)

    debounced('first')
    debounced('second')
    vi.advanceTimersByTime(50)

    expect(fn).toHaveBeenCalledWith('second')
  })

  it('cancel() drops a pending call', () => {
    const fn = vi.fn()
    const debounced = debounce(fn, 50)

    debounced()
    debounced.cancel()
    vi.advanceTimersByTime(50)

    expect(fn).not.toHaveBeenCalled()
  })

  it('fires again after a previous call already resolved', () => {
    const fn = vi.fn()
    const debounced = debounce(fn, 50)

    debounced()
    vi.advanceTimersByTime(50)
    debounced()
    vi.advanceTimersByTime(50)

    expect(fn).toHaveBeenCalledTimes(2)
  })
})
