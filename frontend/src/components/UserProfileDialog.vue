<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useAuth } from '../composables/useAuth'
import { updateProfile, uploadAvatar, getErrorMessage } from '../api'
import { API_BASE_URL } from '../config'

import { useNotification } from '../composables/useNotification'

interface Props {
  show: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'logout'): void
}>()

const { currentUser } = useAuth()
const submitting = ref(false)
const uploading = ref(false)
const avatarVersion = ref(0)
const { showSuccess, showError, hideNotification } = useNotification()
const fileInput = ref<HTMLInputElement | null>(null)
const hasAvatarError = ref(false)

const form = reactive({
  username: '',
  self_description: '',
  major: '',
})

const avatarUrl = computed(() => {
  if (!currentUser.value) return ''
  // 加上时间戳/版本号，以确保头像更换时可以立即刷新
  return `${API_BASE_URL}/auth/avatar/${currentUser.value.uuid}?t=${avatarVersion.value}`
})

// 同步用户信息到表单
function syncForm() {
  if (currentUser.value) {
    form.username = currentUser.value.username || ''
    form.self_description = currentUser.value.self_description || ''
    form.major = currentUser.value.major || ''
  }
}

function handleAvatarError() {
  hasAvatarError.value = true
}

// 监听弹窗显示状态，当打开弹窗时，拉取/同步最新的用户信息
watch(() => props.show, (newVal) => {
  if (newVal) {
    syncForm()
    hideNotification()
  }
})

// 监听 currentUser 变化同步表单
watch(currentUser, () => {
  syncForm()
}, { deep: true })

// 发生头像版本更新或用户改变时，重置头像错误标志
watch([avatarVersion, currentUser], () => {
  hasAvatarError.value = false
})

onMounted(() => {
  syncForm()
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

  try {
    const updatedUser = await uploadAvatar(file)
    if (currentUser.value) {
      currentUser.value.head_file = updatedUser.head_file
    }
    avatarVersion.value++
    window.dispatchEvent(new CustomEvent('learnova-avatar-updated'))
    showSuccess('头像上传成功！')
  } catch (error) {
    showError(getErrorMessage(error))
  } finally {
    uploading.value = false
    target.value = '' // reset input
  }
}

async function handleSaveProfile() {
  if (!form.username.trim()) {
    showError('用户名不能为空。')
    return
  }

  submitting.value = true

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
    showSuccess('个人信息修改成功！')
  } catch (error) {
    showError(getErrorMessage(error))
  } finally {
    submitting.value = false
  }
}

function clickLogout() {
  emit('close')
  emit('logout')
}
</script>

<template>
  <Transition name="dialog-fade">
    <div v-if="show" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm px-4" @click="emit('close')">
      <div class="modal-card relative w-full max-w-[500px] rounded-2xl bg-slate-50/95 p-5 shadow-2xl backdrop-blur-lg border border-slate-200/80 transition-all duration-300 md:p-6" @click.stop>
        
        <!-- Close button -->
        <button
          type="button"
          class="absolute top-4 right-4 text-slate-400 hover:text-slate-700 transition-colors active:scale-95"
          @click="emit('close')"
        >
          <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        <!-- Title -->
        <div class="mb-4">
          <h2 class="text-xl font-bold text-slate-800">个人主页设置</h2>
          <p class="text-xs text-slate-400 mt-1">管理您的个人资料及个性展示</p>
        </div>

        <!-- Content -->
        <div class="space-y-4">
          <!-- Avatar Section -->
          <div class="flex flex-col items-center gap-2">
            <div 
              class="group relative h-20 w-20 cursor-pointer overflow-hidden rounded-full border border-slate-200 bg-slate-200 shadow-md transition-all hover:scale-105 active:scale-95 duration-200 flex items-center justify-center select-none"
              @click="triggerAvatarUpload"
            >
              <!-- 底层灰底首字母占位 -->
              <span class="text-2xl font-bold text-slate-500">
                {{ (currentUser?.username || 'U').slice(0, 1).toUpperCase() }}
              </span>

              <!-- 顶层图片覆盖 -->
              <img 
                v-if="currentUser?.head_file && !hasAvatarError" 
                :src="avatarUrl" 
                class="absolute inset-0 h-full w-full object-cover" 
                alt="User Avatar"
                @error="handleAvatarError"
              />

              <div class="absolute inset-0 flex flex-col items-center justify-center bg-black/60 opacity-0 transition-opacity group-hover:opacity-100 z-10">
                <svg class="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M3 9a2 2 0 012-2h.93a2 2 0 011.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                  <path stroke-linecap="round" stroke-linejoin="round" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                <span class="text-[10px] text-white mt-1">更换头像</span>
              </div>
              <!-- Loading indicator -->
              <div v-if="uploading" class="absolute inset-0 flex items-center justify-center bg-black/40 z-20">
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



          <!-- Form fields -->
          <form class="space-y-3" @submit.prevent="handleSaveProfile">
            <label class="block">
              <span class="block text-xs font-medium text-slate-500 mb-1">用户名</span>
              <input 
                v-model="form.username"
                type="text"
                class="h-10 w-full rounded-xl border border-slate-200/80 bg-white/60 px-3 text-sm text-slate-700 outline-none transition duration-150 focus:bg-white focus:border-slate-400 focus:ring-2 focus:ring-slate-900/5"
                placeholder="请输入您的用户名"
                required
              />
            </label>

            <label class="block">
              <span class="block text-xs font-medium text-slate-500 mb-1">专业 (Major)</span>
              <input 
                v-model="form.major"
                type="text"
                class="h-10 w-full rounded-xl border border-slate-200/80 bg-white/60 px-3 text-sm text-slate-700 outline-none transition duration-150 focus:bg-white focus:border-slate-400 focus:ring-2 focus:ring-slate-900/5"
                placeholder="例如：计算机科学与技术"
              />
            </label>

            <label class="block">
              <span class="block text-xs font-medium text-slate-500 mb-1">自我介绍 / 签名</span>
              <textarea 
                v-model="form.self_description"
                rows="2"
                class="w-full rounded-xl border border-slate-200/80 bg-white/60 p-3 text-sm text-slate-700 outline-none transition duration-150 focus:bg-white focus:border-slate-400 focus:ring-2 focus:ring-slate-900/5 resize-none"
                placeholder="写点什么，向大家介绍一下你自己吧..."
                maxlength="200"
              ></textarea>
            </label>

            <div class="flex items-center justify-between pt-3 border-t border-slate-200/60">
              <!-- Logout action -->
              <button 
                type="button"
                class="flex h-9 items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-xs font-semibold text-[#4b5563] transition-colors hover:bg-[#fee2e2] hover:text-[#b91c1c] active:scale-95"
                @click="clickLogout"
              >
                退出登录
              </button>

              <!-- Save action -->
              <button 
                type="submit"
                class="h-9 rounded-xl bg-slate-900 px-5 text-xs font-semibold text-white shadow-md transition-all duration-200 hover:bg-slate-800 active:scale-95 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-white disabled:text-slate-400 disabled:active:scale-100"
                :disabled="submitting"
              >
                {{ submitting ? '保存中...' : '保存资料' }}
              </button>
            </div>
          </form>
        </div>

      </div>
    </div>
  </Transition>
</template>

<style scoped>
.dialog-fade-enter-active,
.dialog-fade-leave-active {
  transition: opacity 0.2s cubic-bezier(0.25, 1, 0.5, 1);
}
.dialog-fade-enter-active > div,
.dialog-fade-leave-active > div {
  transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.2s ease;
}
.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}
.dialog-fade-enter-from > div,
.dialog-fade-leave-to > div {
  transform: scale(0.96);
  opacity: 0;
}
</style>
