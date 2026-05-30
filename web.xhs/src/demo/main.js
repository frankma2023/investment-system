import { createApp } from 'vue'
import App from './App.vue'

// 复用现有小红书风格CSS
import '@/../shared/css/theme.css'

const app = createApp(App)
app.mount('#app')
