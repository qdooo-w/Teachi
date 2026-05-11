// frontend/src/composables/useAuth.ts
import { reactive, ref, type Ref } from 'vue'
import {
  getCurrentUserId,
  getStoredToken,
  login,
  logout,
  refreshAccessToken,
  register as registerAccount,
  setStoredToken,
  getErrorMessage,
} from '../api'

const LAST_EMAIL_KEY = 'teachi.last_email'

const token = ref<string | null>(getStoredToken())
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
  token.value = (event as CustomEvent<string | null>).detail
}

async function initializeAuth(): Promise<void> {
  try {
    if (!getStoredToken() || !getCurrentUserId()) {
      await refreshAccessToken().catch(() => undefined)
    }
    token.value = getStoredToken()
    if (token.value && onTokenReady) await onTokenReady()
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
    if (onTokenReady) await onTokenReady()
  } catch (error) {
    authError.value = getErrorMessage(error)
  } finally {
    authSubmitting.value = false
  }
}

async function handleLogout(): Promise<void> {
  await logout()
}

function displayUser(): string {
  const savedEmail = localStorage.getItem(LAST_EMAIL_KEY)
  const userId = token.value ? getCurrentUserId() : null
  return savedEmail || (userId ? `${userId.slice(0, 8)}...` : '已登录')
}

export function useAuth() {
  return {
    token: token as Ref<string | null>,
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
