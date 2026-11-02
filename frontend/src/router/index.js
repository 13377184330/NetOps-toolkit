import { createRouter, createWebHistory } from 'vue-router'
import DeviceList from '../views/DeviceList.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'devices', component: DeviceList },
  ],
})

export default router
