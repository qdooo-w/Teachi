<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const email = computed(() => {
  const raw = route.query.email
  if (Array.isArray(raw)) return raw[0] || ''
  return raw ? String(raw) : ''
})

const isReset = computed(() => route.query.is_reset === 'true')
const fallback = computed(() => !email.value)

function goToLogin(): void {
  router.push({ name: 'overview' })
}
</script>

<template>
  <div class="space-y-6 text-center">
    <div class="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[#e5e7eb] text-[#1f2937]">
      <svg class="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 4h16v16H4z" />
        <path d="M22 8l-10 6L2 8" />
        <path d="M2 16l10-6 10 6" />
      </svg>
    </div>

    <div>
      <h1 class="text-3xl font-semibold text-[#1f2937]">验证邮件已发送</h1>
      <p class="mt-3 text-sm leading-7 text-[#4b5563]">
        我们已向 <span class="font-semibold text-[#1f2937]">{{ email || '您填写的邮箱' }}</span> 发送了一封验证邮件。
      </p>
    </div>

    <div class="space-y-4 rounded-2xl border border-[#e5e7eb] bg-[#f9fafb] p-6 text-sm text-[#4b5563]">
      <p>请打开邮箱，点击邮件中的链接完成{{ isReset ? '密码重置' : '注册' }}。</p>
      <p>链接有效期为 <span class="font-semibold">10 分钟</span>。</p>
      <p>如果未收到邮件，请检查垃圾邮箱或稍后重试。</p>
      <p v-if="fallback" class="text-slate-500">如果你未看到邮箱地址，说明当前链接未携带邮箱参数。可直接打开登录页面继续。</p>
    </div>

    <div class="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-center">
      <button
        type="button"
        class="inline-flex justify-center rounded-xl bg-[#1f2937] px-6 py-3 text-sm font-semibold text-white transition-all duration-200 hover:bg-[#111827] active:scale-95"
        @click="goToLogin"
      >
        返回登录
      </button>
    </div>
  </div>
</template>
