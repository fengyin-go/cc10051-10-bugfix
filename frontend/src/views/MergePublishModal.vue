<template>
  <div class="modal-backdrop" data-testid="merge-publish-modal" @click.self="emit('close')">
    <div class="modal publish-modal">
      <h3>合并行发布申请</h3>
      <dl class="detail-grid">
        <dt>合并任务</dt>
        <dd>{{ row.合并任务 }}</dd>
        <dt>候选组</dt>
        <dd data-testid="merge-group">{{ payload?.候选组 ?? row.候选组 }}</dd>
        <dt>合并结果</dt>
        <dd>{{ row.合并结果 || '—' }}</dd>
        <dt>当前状态</dt>
        <dd>{{ row.status }}</dd>
      </dl>
      <p v-if="payload" class="merge-recognized">
        合并侧当前认可：<strong data-testid="merge-recognized">{{ payload.合并侧.认可金记录 || '—' }}</strong>
        <span v-if="payload.合并侧.更正确认号">（更正确认号 {{ payload.合并侧.更正确认号 }}）</span>
      </p>
      <p v-if="message" class="claim-message" data-testid="submit-message">{{ message }}</p>
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

      <table v-if="payload && payload.applications.length" class="data-table">
        <thead>
          <tr>
            <th>受理编号</th><th>状态</th><th>领取状态</th><th>引用金记录</th><th>采用金记录</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="app in payload.applications" :key="app.id" :data-testid="`merge-app-${app.id}`">
            <td>{{ app.申请编号 }}</td>
            <td>
              {{ app.status }}
              <span v-if="app.版本冲突" class="conflict-tag">版本冲突</span>
            </td>
            <td>{{ app.领取状态 }}</td>
            <td>{{ app.引用金记录.join('、') }}</td>
            <td>{{ app.采用金记录 || '—' }}</td>
            <td>
              <button
                class="link"
                type="button"
                :data-testid="`open-application-${app.id}`"
                @click="emit('openDetail', app.id)"
              >
                打开明细
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-hint">该候选组还没有发布申请。</p>

      <div class="page-actions">
        <button class="btn" type="button" @click="emit('close')">关闭</button>
        <button
          class="btn primary"
          type="button"
          data-testid="submit-publish-application"
          :disabled="submitting || row.status !== '已合并'"
          @click="submit"
        >
          {{ submitting ? '提交中…' : '提交发布申请' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  fetchMergePublishApplications,
  submitPublishApplication,
  type MergePublishApplications,
} from '@/domain/golden_merge'
import type { EntryRow } from '@/data/types'

const props = defineProps<{ row: EntryRow }>()
const emit = defineEmits<{ close: []; openDetail: [id: number]; changed: [] }>()

const payload = ref<MergePublishApplications | null>(null)
const message = ref('')
const errorMessage = ref('')
const submitting = ref(false)

async function load() {
  errorMessage.value = ''
  try {
    payload.value = await fetchMergePublishApplications(Number(props.row.id))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发布申请读取失败'
  }
}

async function submit() {
  submitting.value = true
  message.value = ''
  errorMessage.value = ''
  try {
    const result = await submitPublishApplication(Number(props.row.id))
    if (!result.ok) throw new Error(result.message)
    message.value = result.message
    emit('changed')
    await load()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '提交发布申请失败'
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.publish-modal { width: min(720px, 100%); }
.detail-grid { display: grid; grid-template-columns: 110px 1fr; gap: 6px 12px; margin: 0 0 12px; }
.detail-grid dt { color: var(--muted); font-size: 12px; }
.detail-grid dd { margin: 0; font-size: 13px; word-break: break-all; }
.merge-recognized { font-size: 13px; }
.conflict-tag { display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 4px; background: #fef3c7; border: 1px solid #f59e0b; font-size: 11px; }
.empty-hint { color: var(--muted); font-size: 13px; }
.claim-message { color: #15803d; font-size: 13px; }
</style>
