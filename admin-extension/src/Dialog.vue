<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { X } from 'lucide-vue-next';
defineProps<{ title: string; busy?: boolean }>();
const emit = defineEmits<{ close: [] }>();
const element = ref<HTMLDialogElement>();
const dirty = ref(false);
function close() { if (!dirty.value || window.confirm('当前表单有未保存的修改，确认关闭？')) emit('close'); }
onMounted(() => element.value?.showModal());
</script>

<template>
  <dialog ref="element" class="um-admin-dialog" :aria-label="title" :data-dirty="dirty" @input="dirty = true" @change="dirty = true" @cancel.prevent="!busy && close()">
    <header><h2>{{ title }}</h2><button type="button" class="icon" title="关闭" :disabled="busy" @click="close"><X :size="18" /></button></header>
    <slot />
  </dialog>
</template>
