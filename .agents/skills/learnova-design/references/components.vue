<script setup lang="ts">
/**
 * Learnova 深度设计系统参考 (Design System References)
 * 包含了全套系统级组件演示，可直接复制以下 Tailwind CSS 类名组合使用。
 */
import { ref } from 'vue'

const showModal = ref(false)
const inputValue = ref('')
const slateInputValue = ref('')
const chatDraft = ref('')
</script>

<template>
  <div class="relative min-h-screen bg-[#f3f4f6] p-8 text-[#1f2937] font-sans">
    <div class="mx-auto max-w-4xl space-y-12">
      
      <!-- ==============================================
           1. 主应用域 (Main UI Hex 体系)
           ============================================== -->
      <section class="space-y-6">
        <h2 class="text-2xl font-bold font-hans border-b border-[#e5e7eb] pb-2">1. 主应用域基础组件</h2>
        
        <div class="space-y-2">
          <h3 class="text-sm font-medium text-[#6b7280]">1.1 按钮及物理按压反馈</h3>
          <div class="flex items-center gap-4">
            <button class="h-11 rounded-xl bg-[#1f2937] px-6 text-sm font-semibold text-white transition-all duration-200 hover:bg-[#111827] active:scale-95">
              Hex 主按钮
            </button>
            <button class="h-11 rounded-xl border border-[#d1d5db] bg-white px-6 text-sm font-medium text-[#4b5563] transition-colors hover:bg-[#e5e7eb] hover:text-[#1f2937] active:scale-95">
              次要按钮
            </button>
            <!-- 警示性操作红 (Destructive Hover) -->
            <button class="flex h-9 items-center justify-center rounded-lg px-4 text-[#4b5563] transition-colors hover:bg-[#fee2e2] hover:text-[#b91c1c] active:scale-95">
              危险操作
            </button>
          </div>
        </div>

        <div class="space-y-2 max-w-md">
          <h3 class="text-sm font-medium text-[#6b7280]">1.2 基础输入框</h3>
          <input
            v-model="inputValue"
            type="text"
            class="h-11 w-full rounded-lg border border-[#d1d5db] bg-white px-3 text-sm text-[#1f2937] outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
            placeholder="获得焦点查看 Focus Ring..."
          />
        </div>
      </section>

      <!-- ==============================================
           2. 聊天专属组件 (Chat Specifics)
           ============================================== -->
      <section class="space-y-6">
        <h2 class="text-2xl font-bold font-hans border-b border-[#e5e7eb] pb-2 mt-8">2. 聊天核心组件</h2>

        <div class="space-y-6 max-w-2xl">
          <!-- 用户气泡 (User Bubble) + 隐藏操作栏 (Group Hover) -->
          <div class="group flex flex-col items-end gap-1">
            <div class="flex items-center gap-2">
              <!-- 隐藏的操作图标，父级 hover 时显示 -->
              <div class="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                <button class="flex h-6 w-6 items-center justify-center rounded text-[#9ca3af] hover:bg-[#e5e7eb] hover:text-[#4b5563]">
                  <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                </button>
              </div>
              <!-- 超大圆角 rounded-3xl, 浅灰底, 细边框 -->
              <div class="rounded-3xl border border-[#d1d5db] bg-[#e5e7eb] px-5 py-3 text-[15px] leading-relaxed text-[#1f2937]">
                帮我分析一下最近的前端设计语言。
              </div>
            </div>
          </div>

          <!-- 工具调用卡片 (Tool Call) -->
          <div class="flex items-start">
            <div class="flex items-center gap-2.5 rounded-xl border border-[#d1d5db] bg-white p-3 text-sm text-[#374151] w-[240px] shadow-sm">
              <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gray-50 text-gray-500 border border-gray-100">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
              </div>
              <div class="flex-1 truncate">
                <div class="font-medium">搜索资料</div>
                <div class="text-xs text-gray-400">正在检索网页...</div>
              </div>
            </div>
          </div>

          <!-- AI 气泡 (AI Bubble) -->
          <div class="flex items-start">
            <!-- 纯白底, 无边框, 内边距更大 -->
            <div class="rounded-3xl bg-white px-5 py-4 text-[15px] leading-relaxed text-[#1f2937] shadow-sm">
              好的，经过分析，该项目采用了极简的黑白灰搭配少许特制动效。
            </div>
          </div>
        </div>

        <!-- 聊天输入框外壳 (Composer Shell focus-within) -->
        <div class="space-y-2 max-w-2xl mt-8">
          <h3 class="text-sm font-medium text-[#6b7280]">聊天底部输入框 (Focus-within 容器级高亮)</h3>
          <div class="composer-shell relative rounded-2xl border border-[#e5e7eb] bg-white p-4 shadow-sm transition-shadow focus-within:border-[#1f2937] focus-within:ring-2 focus-within:ring-[#1f2937]/20">
            <textarea
              v-model="chatDraft"
              class="composer-textarea w-full resize-none bg-transparent text-[15px] leading-relaxed outline-none placeholder:text-[#9ca3af]"
              rows="1"
              placeholder="发送消息..."
            ></textarea>
            <div class="mt-2 flex justify-end">
              <!-- 发送按钮状态管理 -->
              <button 
                class="flex h-9 items-center justify-center rounded-2xl border border-transparent bg-[#1f2937] px-5 text-white transition hover:bg-[#111827] active:scale-95 disabled:cursor-not-allowed disabled:border-[#d1d5db] disabled:bg-white disabled:text-[#9ca3af] disabled:active:scale-100"
                :disabled="!chatDraft"
              >
                发送
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- ==============================================
           3. 弹窗域/高层级 (Modal UI Slate 体系)
           ============================================== -->
      <section class="space-y-6">
        <h2 class="text-2xl font-bold font-hans border-b border-[#e5e7eb] pb-2 mt-8">3. 弹窗与高层级域 (Slate + 毛玻璃)</h2>
        
        <button 
          @click="showModal = true"
          class="h-10 rounded-lg bg-slate-900 px-5 text-sm font-semibold text-white transition-all duration-200 hover:bg-slate-800 active:scale-95 shadow-md"
        >
          打开毛玻璃高级弹窗
        </button>
        
        <Transition name="dialog-fade">
          <div v-if="showModal" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm px-4" @click.self="showModal = false">
            <div class="w-full max-w-md rounded-2xl bg-slate-50/95 p-6 shadow-2xl backdrop-blur-lg border border-slate-200/80">
              <div class="mb-5 flex items-center justify-between">
                <h3 class="text-lg font-bold text-slate-800">高级设置</h3>
                <button @click="showModal = false" class="text-slate-400 hover:text-slate-700 transition-colors">
                  <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
              <label class="block">
                <span class="block text-xs font-medium text-slate-500 mb-1.5">配置名称 (Slate Focus)</span>
                <input
                  v-model="slateInputValue"
                  type="text"
                  class="h-10 w-full rounded-xl border border-slate-200/80 bg-white/60 px-3 text-sm text-slate-700 outline-none transition duration-150 focus:bg-white focus:border-slate-400 focus:ring-2 focus:ring-slate-900/5"
                  placeholder="例如: GPT-4o"
                />
              </label>
              <div class="mt-8 flex justify-end gap-3">
                <button @click="showModal = false" class="h-9 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50">
                  取消
                </button>
                <button @click="showModal = false" class="h-9 rounded-xl bg-slate-900 px-5 text-sm font-semibold text-white shadow-md transition-all duration-200 hover:bg-slate-800 active:scale-95">
                  保存设置
                </button>
              </div>
            </div>
          </div>
        </Transition>
      </section>

    </div>
  </div>
</template>

<style scoped>
/* 弹窗动效 */
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
