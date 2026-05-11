import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'overview',
    component: () => import('../views/OverviewView.vue'),
    meta: { title: '科目总览' },
  },
  {
    path: '/projects/:pid',
    name: 'subject',
    component: () => import('../views/SubjectView.vue'),
  },
  {
    path: '/projects/:pid/sessions/:sid',
    name: 'chat',
    component: () => import('../views/ChatView.vue'),
  },
  { path: '/:pathMatch(.*)*', redirect: { name: 'overview' } },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  const base = 'Teachi'
  const title = (to.meta?.title as string | undefined) ?? ''
  document.title = title ? `${title} · ${base}` : base
})
