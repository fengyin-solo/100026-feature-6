<template>
  <section class="page" data-module="location">
    <header class="page-head">
      <div>
        <h2>场地租用管理</h2>
        <p class="page-desc">维护拍摄场地，围绕场地编号、场地名称、场地类型、所属区域做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记拍摄场地</button>
        <button class="btn" type="button" @click="downloadTemplate">下载导入模板</button>
        <button class="btn" type="button" :disabled="importing" @click="triggerImport">
          {{ importing ? '导入中…' : '按当前结果导入' }}
        </button>
        <button class="btn" type="button" @click="exportRows">导出场地租用清单</button>
        <input
          ref="fileInput"
          class="hidden-input"
          type="file"
          accept=".csv,text/csv"
          @change="handleFile"
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
      <span v-if="scopeHint" class="scope-hint">导入仅接收符合当前筛选：{{ scopeHint }}</span>
    </form>

    <article v-if="importResult" class="import-panel" :class="{ 'is-warn': importResult.conflicted > 0 || importResult.interrupted }">
      <header class="import-head">
        <strong>{{ importResult.message || '文件导入已处理' }}</strong>
        <div class="import-ops">
          <button
            v-if="importResult.interrupted && lastImportFile"
            class="btn primary"
            type="button"
            :disabled="importing"
            @click="resumeImport"
          >
            从中断项继续（第 {{ (importResult.next_index ?? 0) + 2 }} 行起）
          </button>
          <button class="btn ghost" type="button" @click="importResult = null">关闭报告</button>
        </div>
      </header>
      <p class="import-meta">
        文件：{{ importResult.filename }} ｜ 数据行 {{ importResult.total }} ｜
        新增 {{ importResult.created }} ｜ 冲突 {{ importResult.conflicted }} ｜
        未处理 {{ importResult.skipped }}
      </p>
      <table v-if="importResult.conflicts.length" class="data-table conflict-table">
        <thead>
          <tr>
            <th>文件行号</th>
            <th>场地编号</th>
            <th>场地名称</th>
            <th>场地类型</th>
            <th>可租时段</th>
            <th>冲突原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in importResult.conflicts" :key="item.line">
            <td>第 {{ item.line }} 行</td>
            <td>{{ item.values['场地编号'] || '—' }}</td>
            <td>{{ item.values['场地名称'] || '—' }}</td>
            <td>{{ item.values['场地类型'] || '—' }}</td>
            <td>{{ item.values['可租时段'] || '—' }}</td>
            <td class="error-text">{{ item.reason }}</td>
          </tr>
        </tbody>
      </table>
    </article>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无场地租用数据，可先登记拍摄场地</td>
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

type Row = Record<string, string | number | null>

interface ImportConflict {
  line: number
  values: Record<string, string>
  reason: string
}

interface ImportResult {
  ok: boolean
  message: string
  filename: string | null
  fingerprint: string | null
  scope: Record<string, string>
  total: number
  created: number
  conflicted: number
  skipped: number
  interrupted: boolean
  next_index: number | null
  conflicts: ImportConflict[]
}

const ENDPOINT = '/api/location'
const columns = ["场地编号", "场地名称", "场地类型", "所属区域", "可租时段", "场地费用", "对接联系人", "租用状态"]
const actions = ["签约场地", "确认进场", "办理退场"]
const statuses = ["待洽谈", "已签约", "使用中", "已退场"]
const stats = [{"label": "已签约场地", "value": 0}, {"label": "使用中场地", "value": 0}, {"label": "待洽谈场地", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const fileInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const importResult = ref<ImportResult | null>(null)
const lastImportFile = ref<File | null>(null)

const currentScope = computed(() =>
  Object.fromEntries(Object.entries(filters.value).filter(([, value]) => value?.trim())),
)
const scopeHint = computed(() =>
  Object.entries(currentScope.value).map(([field, value]) => `${field}含「${value}」`).join('，'),
)

function resetFilters() {
  filters.value = {}
  void reload()
}

function currentQuery() {
  return new URLSearchParams(filters.value as Record<string, string>).toString()
}

function exportRows() {
  window.open(`${ENDPOINT}/export?${currentQuery()}`, '_blank')
}

function downloadTemplate() {
  window.open(`${ENDPOINT}/import-template?${currentQuery()}`, '_blank')
}

function triggerImport() {
  importResult.value = null
  fileInput.value?.click()
}

async function handleFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  if (!file) {
    return
  }
  lastImportFile.value = file
  await submitImport(file, false)
}

async function resumeImport() {
  if (lastImportFile.value) {
    await submitImport(lastImportFile.value, true)
  }
}

async function submitImport(file: File, resume: boolean) {
  importing.value = true
  errorMessage.value = ''
  try {
    const content = await file.text()
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, content, scope: currentScope.value, resume }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(payload?.detail ?? '文件导入失败，请检查文件格式')
    }
    importResult.value = payload as ImportResult
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '文件导入失败'
  } finally {
    importing.value = false
  }
}

function openCreate() {
  errorMessage.value = '拍摄场地登记入口尚未接入审批流'
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

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${currentQuery()}`)
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
