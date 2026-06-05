<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getErrorMessage, setPassword, setStoredToken } from '../api'

const route = useRoute()
const router = useRouter()
const tempToken = ref<string>('')
const isReset = ref(false)
const submitting = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const form = reactive({
  username: '',
  password: '',
  confirmPassword: '',
})

const canSubmit = computed(
  () =>
    !!tempToken.value &&
    (isReset.value || form.username.trim()) &&
    form.password.trim() &&
    form.password === form.confirmPassword,
)

onMounted(() => {
  tempToken.value =
    (route.query.temp_token as string | undefined) ||
    (route.query.code as string | undefined) ||
    ''
  isReset.value = route.query.is_reset === 'true'

  if (!tempToken.value) {
    errorMessage.value = '未检测到临时令牌，请通过邮件中的链接访问此页面。'
  }
})

async function handleSubmit(): Promise<void> {
  errorMessage.value = ''
  if (!tempToken.value) {
    errorMessage.value = '未检测到临时令牌，请通过邮件中的链接访问此页面。'
    return
  }
  if (!isReset.value && !form.username.trim()) {
    errorMessage.value = '请输入用户名。'
    return
  }
  if (!form.password.trim()) {
    errorMessage.value = '请输入密码。'
    return
  }
  if (form.password !== form.confirmPassword) {
    errorMessage.value = '两次输入的密码不一致。'
    return
  }
  if (form.password.length < 8) {
    errorMessage.value = '密码长度至少为 8 位。'
    return
  }

  submitting.value = true
  try {
    const result = await setPassword(
      tempToken.value,
      isReset.value ? undefined : form.username.trim(),
      form.password,
    )
    if (result?.access_token) {
      setStoredToken(result.access_token)
    }
    successMessage.value = isReset.value ? '密码重置成功，正在跳转……' : '密码设置成功，正在跳转……'
    setTimeout(() => {
      void router.replace({ name: 'overview' })
    }, 800)
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="min-h-screen bg-slate-100 px-6 py-16 text-slate-900">
    <div class="mx-auto w-full max-w-4xl rounded-[36px] border border-slate-200 bg-white shadow-[0_40px_120px_-50px_rgba(15,23,42,0.2)]">
      <div class="grid gap-6 lg:grid-cols-[0.95fr_0.8fr]">
        <div class="rounded-[36px] bg-slate-950 p-10 text-white sm:p-12 lg:p-14">
          <div class="space-y-6">
            <span class="inline-flex rounded-full bg-white/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-slate-200">
              {{ isReset ? '安全中心' : '账号初始化' }}
            </span>
            <h1 class="text-4xl font-semibold tracking-tight text-white">
              {{ isReset ? '重置账户密码' : '设置密码并完成注册' }}
            </h1>
            <p class="max-w-xl text-base leading-7 text-slate-300">
              {{ isReset ? '请填写您的新密码，系统将自动更新并登录您的账户。' : '请填写用户名和新密码，系统将自动为您创建账户并登录。该页面适用于已完成 NJUtable 邮件验证的用户。' }}
            </p>
          </div>
          <div class="mt-8 rounded-[28px] border border-white/10 bg-white/5 p-6 text-sm text-slate-200 shadow-[0_20px_80px_-40px_rgba(15,23,42,0.5)]">
            <div class="font-semibold text-white">提示</div>
            <ul class="mt-4 space-y-3 text-slate-300">
              <li>• 确保使用邮件链接访问此页面。</li>
              <li>• 密码长度至少 8 位。</li>
              <li>• 如果链接已过期，请重新申请注册或重置密码。</li>
            </ul>
          </div>
        </div>

        <div class="flex flex-col justify-center rounded-[36px] bg-white p-10 shadow-sm sm:p-12 lg:p-14">
          <div v-if="errorMessage" class="mb-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {{ errorMessage }}
          </div>

          <div v-if="successMessage" class="mb-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {{ successMessage }}
          </div>

          <form v-if="!successMessage" class="space-y-5" @submit.prevent="handleSubmit">
          <label v-if="!isReset" class="block">
            <span class="mb-2 block text-sm font-medium text-slate-700">用户名</span>
            <input
              v-model="form.username"
              class="h-12 w-full rounded-2xl border border-slate-200 bg-white px-4 text-slate-900 outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20"
              autocomplete="username"
              type="text"
            />
          </label>

          <label class="block">
            <span class="mb-2 block text-sm font-medium text-slate-700">新密码</span>
            <input
              v-model="form.password"
              class="h-12 w-full rounded-2xl border border-slate-200 bg-white px-4 text-slate-900 outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20"
              autocomplete="new-password"
              type="password"
            />
          </label>

          <label class="block">
            <span class="mb-2 block text-sm font-medium text-slate-700">确认新密码</span>
            <input
              v-model="form.confirmPassword"
              class="h-12 w-full rounded-2xl border border-slate-200 bg-white px-4 text-slate-900 outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20"
              autocomplete="new-password"
              type="password"
            />
          </label>

          <button
            type="submit"
            class="h-12 w-full rounded-2xl bg-slate-900 px-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
            :disabled="submitting || !canSubmit"
          >
            {{ submitting ? '处理中...' : (isReset ? '确认重置并登录' : '设置密码并登录') }}
          </button>
        </form>

        <p class="mt-6 text-sm leading-6 text-slate-500">
          {{ isReset ? '如果您已申请重置密码，请使用最近一次收到的邮件链接访问本页面完成重置。' : '如果您已在 NJUtable 提交注册表单，请使用邮件中的链接访问本页面完成密码设置。' }}
        </p>
      </div>
    </div>
  </div>
  </main>
</template>
