// 后端 API 封装（走 vite 代理，同源无跨域问题）
import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 15000 })

export default {
  // 设备管理
  listDevices(params) {
    return api.get('/devices', { params })
  },
  createDevice(data) {
    return api.post('/devices', data)
  },
  updateDevice(id, data) {
    return api.put(`/devices/${id}`, data)
  },
  deleteDevice(id) {
    return api.delete(`/devices/${id}`)
  },
  testConnection(id) {
    return api.post(`/devices/${id}/test-connection`)
  },
  // 配置生成
  generateVlan(data) {
    return api.post('/generate/vlan', data)
  },
}
