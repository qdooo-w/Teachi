<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getErrorMessage, setPassword, setStoredToken } from '../api'
import { useNotification } from '../composables/useNotification'

const route = useRoute()
const router = useRouter()
const tempToken = ref<string>('')
const isReset = ref(false)
const submitting = ref(false)
const successMessage = ref('')
const { showError } = useNotification()

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
    showError('未检测到临时令牌，请通过邮件中的链接访问此页面。')
  }
})

async function handleSubmit(): Promise<void> {
  if (!tempToken.value) {
    showError('未检测到临时令牌，请通过邮件中的链接访问此页面。')
    return
  }
  if (!isReset.value && !form.username.trim()) {
    showError('请输入用户名。')
    return
  }
  if (!form.password.trim()) {
    showError('请输入密码。')
    return
  }
  if (form.password !== form.confirmPassword) {
    showError('两次输入的密码不一致。')
    return
  }
  if (form.password.length < 8) {
    showError('密码长度至少为 8 位。')
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
    showError('设置密码失败', getErrorMessage(error))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="min-h-screen bg-[#f3f4f6] px-6 py-16 text-[#1f2937]">
    <div class="mx-auto w-full max-w-4xl rounded-2xl border border-[#d1d5db] bg-white shadow-lg">
      <div class="grid gap-6 lg:grid-cols-[0.95fr_0.8fr]">
        <div class="rounded-2xl bg-[#1f2937] p-10 text-white sm:p-12 lg:p-14">
          <div class="space-y-6">
            <span class="inline-flex rounded-full bg-white/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-white/90">
              {{ isReset ? '安全中心' : '账号初始化' }}
            </span>
            <h1 class="text-4xl font-semibold tracking-tight text-white">
              {{ isReset ? '重置账户密码' : '设置密码并完成注册' }}
            </h1>
            <p class="max-w-xl text-base leading-7 text-white/80">
              {{ isReset ? '请填写您的新密码，系统将自动更新并登录您的账户。' : '请填写用户名和新密码，系统将自动为您创建账户并登录。该页面适用于已完成 NJUtable 邮件验证的用户。' }}
            </p>
          </div>
          <div class="mt-8 rounded-xl border border-white/10 bg-white/5 p-6 text-sm text-white/90">
            <div class="font-semibold text-white">提示</div>
            <ul class="mt-4 space-y-3 text-white/70">
              <li>• 确保使用邮件链接访问此页面。</li>
              <li>• 密码长度至少 8 位。</li>
              <li>• 如果链接已过期，请重新申请注册或重置密码。</li>
            </ul>
          </div>
        </div>

        <div class="flex flex-col justify-center rounded-2xl bg-white p-10 sm:p-12 lg:p-14">
          <div v-if="successMessage" class="mb-4 rounded-xl border border-emerald-100 bg-emerald-50/50 px-4 py-3 text-sm text-emerald-700">
            {{ successMessage }}
          </div>

          <form v-if="!successMessage" class="space-y-5" @submit.prevent="handleSubmit">
            <label v-if="!isReset" class="block">
              <span class="mb-2 block text-sm font-medium text-[#4b5563]">用户名</span>
              <input
                v-model="form.username"
                class="h-12 w-full rounded-xl border border-[#d1d5db] bg-white px-4 text-[#1f2937] outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                autocomplete="username"
                type="text"
              />
            </label>

            <label class="block">
              <span class="mb-2 block text-sm font-medium text-[#4b5563]">新密码</span>
              <input
                v-model="form.password"
                class="h-12 w-full rounded-xl border border-[#d1d5db] bg-white px-4 text-[#1f2937] outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                autocomplete="new-password"
                type="password"
              />
            </label>

            <label class="block">
              <span class="mb-2 block text-sm font-medium text-[#4b5563]">确认新密码</span>
              <input
                v-model="form.confirmPassword"
                class="h-12 w-full rounded-xl border border-[#d1d5db] bg-white px-4 text-[#1f2937] outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                autocomplete="new-password"
                type="password"
              />
            </label>

            <button
              type="submit"
              class="h-12 w-full rounded-xl border border-transparent bg-[#1f2937] px-4 text-sm font-semibold text-white transition-all duration-200 hover:bg-[#111827] active:scale-95 disabled:cursor-not-allowed disabled:border-[#d1d5db] disabled:bg-white disabled:text-[#9ca3af] disabled:active:scale-100"
              :disabled="submitting || !canSubmit"
            >
              {{ submitting ? '处理中...' : (isReset ? '确认重置并登录' : '设置密码并登录') }}
            </button>
          </form>

          <p class="mt-6 text-sm leading-6 text-[#9ca3af]">
            {{ isReset ? '如果您已申请重置密码，请使用最近一次收到的邮件链接访问本页面完成重置。' : '如果您已在 NJUtable 提交注册表单，请使用邮件中的链接访问本页面完成密码设置。' }}
          </p>
        </div>
      </div>
    </div>
  </main>
</template>
