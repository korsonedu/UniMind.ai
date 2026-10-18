<script setup lang="ts">
import { useApi } from '@directus/extensions-sdk';
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router';
import { onMounted, onUnmounted } from 'vue';
import AdminNavigation from './AdminNavigation.vue';
import { currentSection } from './navigation';
import Workspace from './Workspace.vue';
import { detail } from './api';
import type { Gateway } from './types';

const api = useApi();
defineProps<{ section?: string }>();
function canNavigate() {
  return !document.querySelector('.um-admin-dialog[data-dirty="true"], .um-admin [data-dirty="true"]') || window.confirm('当前页面有未保存的内容，确认离开？');
}
onBeforeRouteLeave(canNavigate);
onBeforeRouteUpdate(canNavigate);
function beforeUnload(event: BeforeUnloadEvent) {
  if (document.querySelector('.um-admin-dialog[data-dirty="true"], .um-admin [data-dirty="true"]')) { event.preventDefault(); event.returnValue = ''; }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload));
onUnmounted(() => window.removeEventListener('beforeunload', beforeUnload));
const gateway: Gateway = async (operation, payload = {}) => {
  try { return (await api.post(`/unimind-admin-api/operations/${operation}`, payload)).data; }
  catch (error: any) { throw new Error(detail(error.response?.data || error.message)); }
};
</script>

<template>
  <private-view title="UniMind">
    <template #navigation><AdminNavigation :active="currentSection(section)" /></template>
    <Workspace :api="gateway" :section="currentSection(section)" />
  </private-view>
</template>
