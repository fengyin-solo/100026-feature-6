<template>
  <section class="page" data-module="location">
    <header class="page-head">
      <div>
        <h2>场地租用管理</h2>
        <p class="page-desc">维护拍摄场地，围绕场地编号、场地名称、场地类型、所属区域做登记、筛选、导入与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记拍摄场地</button>
        <button class="btn" type="button" :disabled="importing" :title="scopeText || '未设置筛选范围'" @click="triggerImport">
          按当前结果导入文件
        </button>
        <button class="btn" type="button" @click="exportRows">导出场地租用清单</button>
        <input
          ref="fileInput"
          class="import-file"
          type="file"
          accept=".csv,.tsv,.json,application/json,text/csv,text/plain"
          @change="handleFileSelected"
        />
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="importResult" class="import-panel" :class="{ 'has-failure': importResult.failed > 0 || importResult.interrupted }">
      <div class="import-summary">
        <strong>{{ importResult.message }}</strong>
        <span>总数 {{ importResult.total }} / 已处理 {{ importResult.processed }} / 新增 {{ importResult.created }} / 重复 {{ importResult.duplicates }} / 失败 {{ importResult.failed }}</span>
        <span v-if="scopeText">当前范围：{{ scopeText }}</span>
        <button v-if="importResult.interrupted && selectedFile" class="btn" type="button" :disabled="importing" @click="resumeImport">
          从第 {{ (importResult.resume_from ?? 0) + 1 }} 行继续
        </button>
      </div>
      <table v-if="importRows.length" class="data-table import-table">
        <thead>
          <tr>
            <th>文件行</th>
            <th>结果</th>
            <th>原因</th>
            <th>场地名称</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in importRows" :key="item.row" :class="`import-${item.status}`">
            <td>{{ item.row }}</td>
            <td>{{ statusText[item.status] ?? item.status }}</td>
            <td>{{ item.reason || '—' }}</td>
            <td>{{ item.entry?.['场地名称'] ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ displayValue(row, column) }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无场地租用数据，可先登记或导入拍摄场地</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条场地租用记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type ImportRowStatus = 'created' | 'duplicate' | 'failed'
type ImportRowResult = {
  row: number
  status: ImportRowStatus
  reason?: string | null
  entry?: Row | null
}
type ImportResult = {
  ok: boolean
  message: string
  total: number
  processed: number
  created: number
  duplicates: number
  failed: number
  interrupted: boolean
  resume_from?: number | null
  file_fingerprint?: string | null
  scope: Record<string, string>
  rows: ImportRowResult[]
}

const ENDPOINT = '/api/location'
const columns = ["场地编号", "场地名称", "场地类型", "所属区域", "可租时段", "场地费用", "对接联系人", "租用状态"]
const actions = ["签约场地", "确认进场", "办理退场"]
const stats = [{"label": "已签约场地", "value": 0}, {"label": "使用中场地", "value": 0}, {"label": "待洽谈场地", "value": 0}]
const statusText: Record<ImportRowStatus, string> = {
  created: '已新增',
  duplicate: '重复跳过',
  failed: '失败',
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const importing = ref(false)
const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const importResult = ref<ImportResult | null>(null)
const filters = ref<Record<string, string>>({
  场地编号: '',
  场地名称: '',
  场地类型: '',
})
const filterFields = ['场地编号', '场地名称', '场地类型']

const scopeParams = computed<Record<string, string>>(() => {
  const params: Record<string, string> = {}
  if (filters.value['场地编号']) params.keyword = filters.value['场地编号']
  if (filters.value['场地名称']) params.name = filters.value['场地名称']
  if (filters.value['场地类型']) params.location_type = filters.value['场地类型']
  return params
})

const scopeText = computed(() => Object.entries(scopeParams.value)
  .map(([key, value]) => `${filterLabel(key)}包含「${value}」`)
  .join('，'))

const importRows = computed(() => (importResult.value?.rows ?? []).filter(item => item.status !== 'created'))

function filterLabel(key: string) {
  const labels: Record<string, string> = {
    keyword: '场地编号',
    name: '场地名称',
    location_type: '场地类型',
    status: '租用状态',
  }
  return labels[key] ?? key
}

function resetFilters() {
  filters.value = { 场地编号: '', 场地名称: '', 场地类型: '' }
  void reload()
}

function listQuery(extra: Record<string, string> = {}) {
  return new URLSearchParams({ ...scopeParams.value, ...extra }).toString()
}

function exportRows() {
  const query = listQuery()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function triggerImport() {
  errorMessage.value = ''
  fileInput.value?.click()
}

function openCreate() {
  errorMessage.value = '拍摄场地登记入口尚未接入审批流'
}

async function handleFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  selectedFile.value = file
  await sendImport(file, 0)
}

async function resumeImport() {
  if (!selectedFile.value || !importResult.value?.interrupted) {
    return
  }
  await sendImport(selectedFile.value, importResult.value.resume_from ?? 0)
}

async function sendImport(file: File, startRow: number) {
  importing.value = true
  errorMessage.value = ''
  try {
    const content = await file.text()
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      body: JSON.stringify({
        filename: file.name,
        content,
        start_row: startRow,
        ...scopeParams.value,
      }),
    })
    const payload = await response.json() as ImportResult
    if (!response.ok) {
      throw new Error(payload.message || '场地文件导入失败')
    }
    importResult.value = payload
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场地文件导入失败'
  } finally {
    importing.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('场地租用动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场地租用操作失败'
  }
}

function displayValue(row: Row, column: string) {
  if (column === '租用状态') {
    return row[column] ?? row.status ?? '—'
  }
  return row[column] ?? '—'
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${listQuery({ page: '1', size: '200' })}`)
    if (!response.ok) {
      throw new Error('拍摄场地列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '场地租用列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.import-file {
  display: none;
}

.import-panel {
  margin: 0 0 12px;
  padding: 10px 12px;
  border: 1px solid #b2ccf8;
  border-radius: 8px;
  background: #f8fbff;
}

.import-panel.has-failure {
  border-color: #f3b44b;
  background: #fffaf0;
}

.import-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
}

.import-table th,
.import-table td {
  font-size: 12px;
}

.import-duplicate td {
  color: #64748b;
}

.import-failed td {
  color: #b42318;
}
</style>
