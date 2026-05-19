// frontend/src/composables/useAuth.ts
import { reactive, ref, type Ref } from 'vue'
import {
  getCurrentUser,
  getCurrentUserId,
  getStoredToken,
  login,
  logout,
  refreshAccessToken,
  register as registerAccount,
  setStoredToken,
  getErrorMessage,
  type UserOut,
} from '../api'
import { LAST_EMAIL_KEY } from '../config'

const token = ref<string | null>(getStoredToken())
const currentUser = ref<UserOut | null>(null)
const bootstrapping = ref(true)
const preparing = ref(false)
const authSubmitting = ref(false)
const authError = ref('')
const errorMessage = ref('')

const authMode = ref<'login' | 'register'>('login')
const authForm = reactive({
  username: '',
  email: localStorage.getItem(LAST_EMAIL_KEY) || '',
  password: '',
})

// onTokenReady：登录 / 启动恢复成功后的钩子，调用方（App / router）注入
let onTokenReady: (() => Promise<void>) | null = null

function setOnTokenReady(fn: () => Promise<void>): void {
  onTokenReady = fn
}

function handleTokenChange(event: Event): void {
  const next = (event as CustomEvent<string | null>).detail
  token.value = next
  // token 被清掉（如 401 刷新失败）时同步清缓存的用户信息
  if (!next) currentUser.value = null
}

// 拉取并缓存当前登录用户信息；失败时不阻断整体流程，只记录用于回退展示。
async function refreshCurrentUser(): Promise<void> {
  if (!getStoredToken()) {
    currentUser.value = null
    return
  }
  try {
    currentUser.value = await getCurrentUser()
  } catch {
    currentUser.value = null
  }
}

async function initializeAuth(): Promise<void> {
  try {
    if (!getStoredToken() || !getCurrentUserId()) {
      await refreshAccessToken().catch(() => undefined)
    }
    token.value = getStoredToken()
    if (token.value) {
      await refreshCurrentUser()
      if (onTokenReady) await onTokenReady()
    }
  } catch (error) {
    const message = getErrorMessage(error)
    errorMessage.value = message
    authError.value = message
    setStoredToken(null)
  } finally {
    bootstrapping.value = false
  }
}

async function submitAuth(): Promise<void> {
  authError.value = ''
  errorMessage.value = ''

  if (!authForm.email.trim() || !authForm.password.trim()) {
    authError.value = '请输入邮箱和密码。'
    return
  }
  if (authMode.value === 'register' && !authForm.username.trim()) {
    authError.value = '请输入用户名。'
    return
  }

  authSubmitting.value = true
  try {
    if (authMode.value === 'register') {
      await registerAccount(authForm.username.trim(), authForm.email.trim(), authForm.password)
    }
    await login(authForm.email.trim(), authForm.password)
    localStorage.setItem(LAST_EMAIL_KEY, authForm.email.trim())
    await refreshCurrentUser()
    if (onTokenReady) await onTokenReady()
  } catch (error) {
    authError.value = getErrorMessage(error)
  } finally {
    authSubmitting.value = false
  }
}

async function handleLogout(): Promise<void> {
  await logout()
  currentUser.value = null
}

function displayUser(): string {
  if (currentUser.value?.username) return currentUser.value.username
  const savedEmail = currentUser.value?.email || localStorage.getItem(LAST_EMAIL_KEY)
  const userId = token.value ? getCurrentUserId() : null
  return savedEmail || (userId ? `${userId.slice(0, 8)}...` : '已登录')
}

export function useAuth() {
  return {
    token: token as Ref<string | null>,
    currentUser,
    bootstrapping,
    preparing,
    authSubmitting,
    authError,
    errorMessage,
    authMode,
    authForm,
    initializeAuth,
    submitAuth,
    handleLogout,
    handleTokenChange,
    setOnTokenReady,
    displayUser,
    LAST_EMAIL_KEY,
  }
}
