<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useAuth } from '../composables/useAuth'
import { updateProfile, uploadAvatar, getErrorMessage } from '../api'
import { API_BASE_URL } from '../config'

interface Props {
  show: boolean
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const { currentUser, handleLogout } = useAuth()
const submitting = ref(false)
const uploading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const avatarVersion = ref(0)
const fileInput = ref<HTMLInputElement | null>(null)

const form = reactive({
  username: currentUser.value?.username || '',
  self_description: currentUser.value?.self_description || '',
  major: currentUser.value?.major || '',
})

const avatarUrl = computed(() => {
  if (!currentUser.value) return ''
  // 加上时间戳/版本号，以确保头像更换时可以立即刷新
  return `${API_BASE_URL}/auth/avatar/${currentUser.value.uuid}?t=${avatarVersion.value}`
})

// 监听 currentUser 变化同步表单
onMounted(() => {
  if (currentUser.value) {
    form.username = currentUser.value.username || ''
    form.self_description = currentUser.value.self_description || ''
    form.major = currentUser.value.major || ''
  }
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') emit('close')
}

function triggerAvatarUpload() {
  if (fileInput.value) {
    fileInput.value.click()
  }
}

async function handleAvatarChange(event: Event) {
  const target = event.target as HTMLInputElement
  const files = target.files
  if (!files || files.length === 0) return

  const file = files[0]
  uploading.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    const updatedUser = await uploadAvatar(file)
    if (currentUser.value) {
      currentUser.value.head_file = updatedUser.head_file
    }
    avatarVersion.value++
    window.dispatchEvent(new CustomEvent('learnova-avatar-updated'))
    successMessage.value = '头像上传成功！'
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    uploading.value = false
    target.value = '' // reset input
  }
}

async function handleSaveProfile() {
  if (!form.username.trim()) {
    errorMessage.value = '用户名不能为空。'
    return
  }

  submitting.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    const updatedUser = await updateProfile(
      form.username.trim(),
      form.self_description.trim() || null,
      form.major.trim() || null,
    )
    if (currentUser.value) {
      currentUser.value.username = updatedUser.username
      currentUser.value.self_description = updatedUser.self_description
      currentUser.value.major = updatedUser.major
    }
    successMessage.value = '个人信息修改成功！'
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    submitting.value = false
  }
}

function clickLogout() {
  emit('close')
  void handleLogout()
}
</script>

<template>
  <div v-if="show" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm px-4" @click="emit('close')">
    <div class="modal-card relative w-full max-w-[500px] rounded-3xl bg-white p-6 shadow-2xl transition-all duration-300 md:p-8" @click.stop>
      
      <!-- Close button -->
      <button
        type="button"
        class="absolute top-5 right-5 text-slate-400 hover:text-slate-600 transition-colors"
        @click="emit('close')"
      >
        <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      <!-- Title -->
      <div class="mb-6">
        <h2 class="text-xl font-bold text-slate-900">个人主页设置</h2>
        <p class="text-xs text-slate-500 mt-1">管理您的个人资料及个性展示</p>
      </div>

      <!-- Content -->
      <div class="space-y-6">
        <!-- Avatar Section -->
        <div class="flex flex-col items-center gap-3">
          <div 
            class="group relative h-24 w-24 cursor-pointer overflow-hidden rounded-full border-2 border-slate-200 shadow-md transition-all hover:scale-105"
            @click="triggerAvatarUpload"
          >
            <img :src="avatarUrl" class="h-full w-full object-cover" alt="User Avatar" />
            <div class="absolute inset-0 flex flex-col items-center justify-center bg-black/60 opacity-0 transition-opacity group-hover:opacity-100">
              <svg class="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M3 9a2 2 0 012-2h.93a2 2 0 011.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span class="text-[10px] text-white mt-1">更换头像</span>
            </div>
            <!-- Loading indicator -->
            <div v-if="uploading" class="absolute inset-0 flex items-center justify-center bg-black/40">
              <div class="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent"></div>
            </div>
          </div>
          <input 
            ref="fileInput" 
            type="file" 
            class="hidden" 
            accept="image/*" 
            @change="handleAvatarChange" 
          />
        </div>

        <!-- Messages -->
        <div v-if="errorMessage" class="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2.5 text-xs text-rose-700">
          {{ errorMessage }}
        </div>
        <div v-if="successMessage" class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs text-emerald-700">
          {{ successMessage }}
        </div>

        <!-- Form fields -->
        <form class="space-y-4" @submit.prevent="handleSaveProfile">
          <div>
            <label class="block text-xs font-semibold text-slate-700 mb-1.5">用户名</label>
            <input 
              v-model="form.username"
              type="text"
              class="h-10 w-full rounded-xl border border-slate-200 px-3.5 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/15"
              placeholder="请输入您的用户名"
              required
            />
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-700 mb-1.5">专业 (Major)</label>
            <input 
              v-model="form.major"
              type="text"
              class="h-10 w-full rounded-xl border border-slate-200 px-3.5 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/15"
              placeholder="例如：计算机科学与技术"
            />
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-700 mb-1.5">自我介绍 / 签名</label>
            <textarea 
              v-model="form.self_description"
              rows="3"
              class="w-full rounded-xl border border-slate-200 p-3.5 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/15 resize-none"
              placeholder="写点什么，向大家介绍一下你自己吧..."
              maxlength="200"
            ></textarea>
          </div>

          <div class="flex items-center justify-between pt-4 border-t border-slate-100">
            <!-- Logout action -->
            <button 
              type="button"
              class="inline-flex h-9 items-center justify-center rounded-xl border border-rose-200 bg-rose-50 px-4 text-xs font-semibold text-rose-700 transition hover:bg-rose-100"
              @click="clickLogout"
            >
              退出登录
            </button>

            <!-- Save action -->
            <button 
              type="submit"
              class="inline-flex h-9 items-center justify-center rounded-xl bg-[#1f2937] px-5 text-xs font-semibold text-white transition hover:bg-[#111827] disabled:opacity-50"
              :disabled="submitting"
            >
              {{ submitting ? '保存中...' : '保存资料' }}
            </button>
          </div>
        </form>
      </div>

    </div>
  </div>
</template>
