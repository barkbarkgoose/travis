<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const isAuthenticated = computed(() => authStore.isAuthenticated)
const isMenuOpen = ref(false)
const profileMenu = ref<HTMLElement | null>(null)

// Below `sm` the link row is hidden (see the template) in favor of this
// hamburger-toggled panel — without it, mobile had no way to reach the nav at all.
const isMobileMenuOpen = ref(false)
const mobileNav = ref<HTMLElement | null>(null)

const displayName = computed(() => authStore.user?.name || authStore.user?.email || 'Account')
const email = computed(() =>
  authStore.user?.role === 'family' ? authStore.user?.email || '' : 'Visitor'
)
const initials = computed(() => {
  const name = authStore.user?.name?.trim()
  if (name) {
    return name
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0])
      .join('')
      .toUpperCase()
  }
  return authStore.user?.email?.charAt(0).toUpperCase() || 'U'
})

const navItems = [
  { name: 'Home', path: '/dashboard' },
  { name: 'Calendar', path: '/calendar' },
  { name: 'My entries', path: '/entries' },
  { name: 'Log a visit', path: '/entries/new' }
]

function handleLogout() {
  isMenuOpen.value = false
  authStore.logout()
  router.push('/login')
}

function closeMenu() {
  isMenuOpen.value = false
}

function closeMobileMenu() {
  isMobileMenuOpen.value = false
}

function handleDocumentClick(event: MouseEvent) {
  if (profileMenu.value && !profileMenu.value.contains(event.target as Node)) {
    closeMenu()
  }
  if (mobileNav.value && !mobileNav.value.contains(event.target as Node)) {
    closeMobileMenu()
  }
}

// Never leave the panel open pointing at a page the user has already left.
watch(() => route.path, closeMobileMenu)

onMounted(() => document.addEventListener('click', handleDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', handleDocumentClick))
</script>

<template>
  <nav v-if="isAuthenticated" class="bg-white shadow-sm border-b border-gray-200">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex h-16 items-center justify-between">
        <!-- Logo -->
        <router-link to="/dashboard" class="flex-shrink-0">
          <span class="font-display text-xl font-semibold text-ink">Travis's Recovery</span>
        </router-link>

        <!-- Nav Links (desktop) -->
        <div class="hidden sm:flex sm:items-center sm:space-x-1">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            :class="route.path === item.path
              ? 'bg-primary text-white'
              : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'"
          >
            {{ item.name }}
          </router-link>
        </div>

        <!-- Mobile toggle + profile menu, grouped so justify-between keeps both on the right -->
        <div class="flex items-center gap-1">
          <!-- Mobile nav toggle: the link row above is hidden below `sm`, so this is
               the only way to reach Calendar/My entries/etc. on a phone. -->
          <div ref="mobileNav" class="relative sm:hidden">
            <button
              type="button"
              aria-label="Toggle navigation menu"
              :aria-expanded="isMobileMenuOpen"
              class="rounded-lg p-2 text-gray-500 transition-colors hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary/40"
              @click.stop="isMobileMenuOpen = !isMobileMenuOpen"
            >
              <svg v-if="!isMobileMenuOpen" class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />
              </svg>
              <svg v-else class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <div
              v-if="isMobileMenuOpen"
              class="absolute right-0 top-full z-20 mt-2 w-56 origin-top-right rounded-2xl border border-gray-200 bg-white p-2 shadow-xl ring-1 ring-black/5"
              role="menu"
            >
              <router-link
                v-for="item in navItems"
                :key="item.path"
                :to="item.path"
                role="menuitem"
                class="block rounded-xl px-3 py-2.5 text-sm font-medium transition-colors"
                :class="route.path === item.path
                  ? 'bg-primary text-white'
                  : 'text-gray-700 hover:bg-gray-50 hover:text-gray-900'"
                @click="closeMobileMenu"
              >
                {{ item.name }}
              </router-link>
            </div>
          </div>

          <!-- Profile menu -->
          <div ref="profileMenu" class="relative">
            <button
              type="button"
              aria-label="Open account menu"
              :aria-expanded="isMenuOpen"
              class="flex items-center gap-2 rounded-full p-1.5 text-left transition-colors hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary/40"
              @click.stop="isMenuOpen = !isMenuOpen"
              @keydown.esc="closeMenu"
            >
              <span class="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-bold text-white shadow-sm">
                {{ initials }}
              </span>
              <span class="hidden max-w-32 text-sm font-medium text-gray-700 sm:block truncate">
                {{ displayName }}
              </span>
              <svg class="hidden h-4 w-4 text-gray-400 sm:block" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.51a.75.75 0 01-1.08 0l-4.25-4.51a.75.75 0 01.02-1.06z" clip-rule="evenodd" />
              </svg>
            </button>

            <div
              v-if="isMenuOpen"
              class="absolute right-0 z-20 mt-2 w-64 origin-top-right rounded-2xl border border-gray-200 bg-white p-2 shadow-xl ring-1 ring-black/5"
              role="menu"
            >
              <div class="border-b border-gray-100 px-3 py-3">
                <p class="truncate text-sm font-semibold text-gray-900">{{ displayName }}</p>
                <p class="mt-0.5 truncate text-xs text-gray-500">{{ email }}</p>
              </div>
              <button
                type="button"
                role="menuitem"
                class="mt-2 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-red-50 hover:text-red-700"
                @click="handleLogout"
              >
                <svg class="h-5 w-5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6A2.25 2.25 0 005.25 5.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 12h9m0 0l-3-3m3 3l-3 3" />
                </svg>
                Log out
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </nav>
</template>
