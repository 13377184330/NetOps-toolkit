<template>
  <div class="page">
    <header class="header">
      <div class="header-left">
        <h1>NetOps Toolkit</h1>
        <span class="subtitle">网络设备配置自动化平台</span>
      </div>
      <el-tag type="info" effect="plain">M1 · 设备管理</el-tag>
    </header>

    <!-- 工具栏 -->
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索名称 / IP / 型号"
        clearable
        style="width: 240px"
        @keyup.enter="loadDevices"
        @clear="loadDevices"
      />
      <el-select v-model="vendorFilter" placeholder="全部厂商" clearable style="width: 150px" @change="loadDevices">
        <el-option v-for="v in vendorOptions" :key="v.value" :label="v.label" :value="v.value" />
      </el-select>
      <el-button type="primary" @click="loadDevices">查询</el-button>
      <div style="flex: 1" />
      <el-button type="primary" @click="openCreate">+ 新增设备</el-button>
    </div>

    <!-- 设备表格 -->
    <el-table :data="devices" v-loading="loading" stripe border style="width: 100%">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="设备名称" min-width="130" />
      <el-table-column prop="ip" label="管理 IP" width="130" />
      <el-table-column prop="ssh_port" label="SSH 端口" width="90" align="center" />
      <el-table-column label="厂商" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="vendorTagType(row.vendor)" effect="light">{{ vendorLabel(row.vendor) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="model" label="型号" width="120" />
      <el-table-column label="角色" width="90" align="center">
        <template #default="{ row }">{{ roleLabel(row.role) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" effect="dark" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_check" label="最后检查" width="165">
        <template #default="{ row }">{{ formatTime(row.last_check) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="success" plain :loading="testingId === row.id" @click="testConn(row)">测试连通</el-button>
          <el-button size="small" plain @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="removeDevice(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @change="loadDevices"
      />
    </div>

    <!-- 新增 / 编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑设备' : '新增设备'" width="520px" destroy-on-close>
      <el-form :model="form" label-width="95px">
        <el-form-item label="设备名称" required>
          <el-input v-model="form.name" placeholder="如：核心-S9306" />
        </el-form-item>
        <el-form-item label="管理 IP" required>
          <el-input v-model="form.ip" placeholder="192.168.1.1" />
        </el-form-item>
        <el-form-item label="SSH 端口">
          <el-input-number v-model="form.ssh_port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="厂商">
          <el-select v-model="form.vendor" style="width: 100%">
            <el-option v-for="v in vendorOptions" :key="v.value" :label="v.label" :value="v.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="型号">
          <el-input v-model="form.model" placeholder="S5735 / S6520 ..." />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="接入层" value="access" />
            <el-option label="核心层" value="core" />
            <el-option label="出口" value="exit" />
            <el-option label="数据中心" value="dc" />
          </el-select>
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="登录账号" />
        </el-form-item>
        <el-form-item :label="editingId ? '密码（不改留空）' : '密码'">
          <el-input v-model="form.password" type="password" show-password placeholder="加密存储" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveDevice">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/device'

const devices = ref([])
const loading = ref(false)
const keyword = ref('')
const vendorFilter = ref('')
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)

const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const testingId = ref(null)

const form = reactive({
  name: '', ip: '', ssh_port: 22, vendor: 'huawei', model: '',
  role: 'access', username: '', password: '', notes: '',
})

const vendorOptions = [
  { label: '华为', value: 'huawei' },
  { label: 'H3C', value: 'h3c' },
  { label: '锐捷', value: 'ruijie' },
  { label: '迈普', value: 'maipu' },
  { label: '思科', value: 'cisco' },
]

const vendorLabel = (v) => ({ huawei: '华为', h3c: 'H3C', ruijie: '锐捷', maipu: '迈普', cisco: '思科' }[v] || v)
const vendorTagType = (v) => ({ huawei: 'danger', h3c: 'warning', ruijie: 'primary', maipu: 'success', cisco: 'info' }[v] || 'info')
const roleLabel = (r) => ({ access: '接入', core: '核心', exit: '出口', dc: '数据中心' }[r] || r)
const statusLabel = (s) => ({ online: '在线', offline: '离线', unknown: '未知' }[s] || s)
const statusTagType = (s) => ({ online: 'success', offline: 'danger', unknown: 'info' }[s] || 'info')
const formatTime = (t) => (t ? String(t).replace('T', ' ').slice(0, 19) : '—')

async function loadDevices() {
  loading.value = true
  try {
    const { data } = await api.listDevices({
      page: page.value, page_size: pageSize.value,
      keyword: keyword.value, vendor: vendorFilter.value,
    })
    devices.value = data.items
    total.value = data.total
  } catch (e) {
    ElMessage.error('加载设备列表失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', ip: '', ssh_port: 22, vendor: 'huawei', model: '', role: 'access', username: '', password: '', notes: '' })
  dialogVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  Object.assign(form, {
    name: row.name, ip: row.ip, ssh_port: row.ssh_port, vendor: row.vendor,
    model: row.model, role: row.role, username: row.username, password: '', notes: row.notes,
  })
  dialogVisible.value = true
}

async function saveDevice() {
  if (!form.name || !form.ip) {
    ElMessage.warning('设备名称和管理 IP 必填')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api.updateDevice(editingId.value, form)
      ElMessage.success('已更新')
    } else {
      await api.createDevice(form)
      ElMessage.success('已新增')
    }
    dialogVisible.value = false
    await loadDevices()
  } catch (e) {
    ElMessage.error('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function removeDevice(row) {
  await ElMessageBox.confirm(`确定删除设备「${row.name}」（${row.ip}）？`, '删除确认', { type: 'warning' })
  try {
    await api.deleteDevice(row.id)
    ElMessage.success('已删除')
    await loadDevices()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

async function testConn(row) {
  testingId.value = row.id
  try {
    const { data } = await api.testConnection(row.id)
    if (data.success) {
      ElMessage.success(`「${row.name}」连通正常（${data.latency_ms} ms）`)
    } else {
      ElMessage.error(`「${row.name}」${data.message}`)
    }
    await loadDevices()
  } catch (e) {
    ElMessage.error('测试失败：' + (e.response?.data?.detail || e.message))
  } finally {
    testingId.value = null
  }
}

onMounted(loadDevices)
</script>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; padding: 20px; }
.header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.header h1 { font-size: 22px; color: #1f2d3d; }
.subtitle { color: #8492a6; font-size: 13px; }
.toolbar { display: flex; gap: 10px; margin-bottom: 14px; align-items: center; }
.pagination { margin-top: 14px; display: flex; justify-content: flex-end; }
</style>
