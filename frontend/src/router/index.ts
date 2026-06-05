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
  {
    path: '/community',
    name: 'community',
    component: () => import('../views/CommunityView.vue'),
    meta: { title: '社区' },
  },
  {
    path: '/set-password',
    name: 'set-password',
    component: () => import('../views/SetPasswordView.vue'),
    meta: { title: '设置密码' },
  },
  {
    path: '/register/confirm',
    name: 'register-confirm',
    component: () => import('../views/RegisterConfirm.vue'),
    meta: { title: '注册确认' },
  },
  { path: '/:pathMatch(.*)*', redirect: { name: 'overview' } },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  // 仅在路由提供静态 title 时覆盖，否则保留当前（通常是上一个视图设置的动态）title
  // 等视图内的 watch 补上动态 title。避免 subject/chat 进入时闪烁为裸 "Learnova"。
  const title = to.meta?.title as string | undefined
  if (title) document.title = `${title} · Learnova`
})
