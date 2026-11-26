<template>
  <div class="modal-backdrop" data-testid="publish-application-panel" @click.self="emit('close')">
    <div class="modal publish-modal">
      <h3>发布申请明细</h3>
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
      <template v-if="detail">
        <dl class="detail-grid">
          <dt>受理编号</dt>
          <dd data-testid="app-acceptance">{{ detail.申请编号 || '—' }}</dd>
          <dt>发布批次</dt>
          <dd>{{ detail.发布批次 }}</dd>
          <dt>当前状态</dt>
          <dd>{{ detail.status }}（领取状态：{{ detail.领取状态 }}）</dd>
          <dt>候选组</dt>
          <dd>{{ detail.候选组 || '—' }}</dd>
          <dt>实体编码</dt>
          <dd>{{ detail.实体编码 }}</dd>
          <dt>原引用金记录</dt>
          <dd data-testid="app-refs">{{ detail.引用金记录.join('、') || '—' }}</dd>
        </dl>

        <p v-if="detail.版本冲突 && !detail.已发出" class="conflict-banner" data-testid="version-conflict">
          版本冲突：原申请引用 {{ detail.引用金记录.join('、') }}，合并侧已确认替代为
          {{ detail.合并侧.认可金记录 }}（更正确认号 {{ detail.合并侧.更正确认号 }}）。
        </p>

        <section class="panel-section">
          <h4>合并侧当前认可</h4>
          <dl class="detail-grid">
            <dt>认可金记录</dt>
            <dd data-testid="recognized-golden">{{ detail.合并侧.认可金记录 || '—' }}</dd>
            <dt>更正确认号</dt>
            <dd data-testid="correction-no">{{ detail.合并侧.更正确认号 || '—' }}</dd>
          </dl>
          <ul v-if="detail.合并侧.替代关系.length" class="replacement-list" data-testid="replacement-list">
            <li v-for="item in detail.合并侧.替代关系" :key="item.更正确认号">
              {{ item.被替代金记录 }} → {{ item.替代为金记录 }}（{{ item.更正确认号 }}）
            </li>
          </ul>
        </section>

        <section class="panel-section">
          <h4>
            发布明细
            <span v-if="detail.已发出" class="frozen-note">（已正式发出，不可改动）</span>
          </h4>
          <table v-if="detail.发布明细.length" class="data-table">
            <thead>
              <tr><th>金记录标识</th><th>确认类型</th><th>更正确认号</th><th>合并任务</th></tr>
            </thead>
            <tbody>
              <tr v-for="line in detail.发布明细" :key="line.金记录标识">
                <td data-testid="detail-golden">{{ line.金记录标识 }}</td>
                <td>{{ line.确认类型 }}</td>
                <td>{{ line.更正确认号 || '—' }}</td>
                <td>{{ line.合并任务 || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="empty-hint">尚未领取确认，领取时按合并侧当前认可结果生成明细。</p>
        </section>

        <p v-if="detail.已发出" class="frozen-note">
          {{ detail.版本标识 }} 于 {{ detail.发布时间 }} 发出，清单保留原金记录标识。
          <span v-if="detail.核对说明">核对说明：{{ detail.核对说明 }}</span>
        </p>
        <p v-if="claimMessage" class="claim-message" data-testid="claim-message">{{ claimMessage }}</p>

        <div class="page-actions">
          <button class="btn" type="button" @click="emit('close')">关闭</button>
          <button class="btn" type="button" data-testid="refresh-application" @click="load">
            刷新核对
          </button>
          <button
            v-if="detail.可领取"
            class="btn primary"
            type="button"
            data-testid="claim-application"
            :disabled="claiming"
            @click="claim"
          >
            {{ claiming ? '领取中…' : detail.领取状态 === '已领取' ? '续领确认' : '领取确认' }}
          </button>
        </div>
      </template>
      <p v-else>加载中…</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  claimPublishApplication,
  fetchPublishApplication,
  type PublishApplicationDetail,
} from '@/domain/golden_publish'

const props = defineProps<{ publishId: number }>()
const emit = defineEmits<{ close: []; changed: [] }>()

const detail = ref<PublishApplicationDetail | null>(null)
const errorMessage = ref('')
const claimMessage = ref('')
const claiming = ref(false)

async function load() {
  errorMessage.value = ''
  try {
    detail.value = await fetchPublishApplication(props.publishId)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发布申请明细读取失败'
  }
}

async function claim() {
  claiming.value = true
  errorMessage.value = ''
  claimMessage.value = ''
  try {
    const result = await claimPublishApplication(props.publishId)
    if (!result.ok) throw new Error(result.message)
    claimMessage.value = result.message
    emit('changed')
    await load()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '领取失败'
  } finally {
    claiming.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.publish-modal { width: min(680px, 100%); }
.detail-grid { display: grid; grid-template-columns: 110px 1fr; gap: 6px 12px; margin: 0 0 12px; }
.detail-grid dt { color: var(--muted); font-size: 12px; }
.detail-grid dd { margin: 0; font-size: 13px; word-break: break-all; }
.panel-section { border-top: 1px solid var(--border); padding-top: 10px; margin-bottom: 12px; }
.panel-section h4 { margin: 0 0 8px; font-size: 13px; }
.conflict-banner { background: #fef3c7; border: 1px solid #f59e0b; border-radius: 6px; padding: 8px 10px; font-size: 13px; }
.replacement-list { margin: 6px 0 0; padding-left: 18px; font-size: 13px; }
.frozen-note { color: var(--muted); font-size: 12px; }
.empty-hint { color: var(--muted); font-size: 13px; }
.claim-message { color: #15803d; font-size: 13px; }
</style>
