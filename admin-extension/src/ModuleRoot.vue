<script setup lang="ts">
import { useApi } from '@directus/extensions-sdk';
import Workspace from './Workspace.vue';
import { detail } from './api';
import type { Gateway } from './types';

const api = useApi();
const gateway: Gateway = async (operation, payload = {}) => {
  try { return (await api.post(`/unimind-admin-api/operations/${operation}`, payload)).data; }
  catch (error: any) { throw new Error(detail(error.response?.data || error.message)); }
};
</script>

<template><private-view title="UniMind"><Workspace :api="gateway" /></private-view></template>
