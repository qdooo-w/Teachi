import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import { CHAT_COMPOSER_MAX_HEIGHT } from './config'
import 'katex/dist/katex.min.css'
import './style.css'

document.documentElement.style.setProperty('--composer-max-height', `${CHAT_COMPOSER_MAX_HEIGHT}px`)

createApp(App).use(router).mount('#app')
