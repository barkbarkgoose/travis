import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue')
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresGuest: true }
  },
  {
    path: '/join/:token',
    name: 'join',
    component: () => import('@/views/JoinView.vue')
  },
  {
    path: '/account',
    name: 'account',
    component: () => import('@/views/AccountView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/admin-signin',
    name: 'admin-signin',
    component: () => import('@/views/AdminSigninView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/calendar',
    name: 'calendar',
    component: () => import('@/views/CalendarView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/entries',
    name: 'my-entries',
    component: () => import('@/views/MyEntriesView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/entries/new',
    name: 'new-entry',
    component: () => import('@/views/NewEntryView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/entries/:id',
    name: 'entry-detail',
    component: () => import('@/views/EntryDetailView.vue'),
    meta: { requiresAuth: true }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()
  // Renews an expired access token from the refresh token when it can, and
  // drops the session when it can't, so isAuthenticated below is trustworthy.
  await authStore.restoreSession()

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else if (
    authStore.isAuthenticated &&
    authStore.needsAccountSetup &&
    to.meta.requiresAuth &&
    to.name !== 'account'
  ) {
    // Family without a passkey session, or a visitor with no password yet.
    next({ name: 'account' })
  } else if (to.meta.requiresGuest && authStore.isAuthenticated) {
    next({ name: 'dashboard' })
  } else {
    next()
  }
})

export default router
