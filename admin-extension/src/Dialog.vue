<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { X } from 'lucide-vue-next';
const props = defineProps<{ title: string; busy?: boolean; dirty?: boolean; wide?: boolean }>();
const emit = defineEmits<{ close: [] }>();
const element = ref<HTMLDialogElement>();
const edited = ref(false);
const isDirty = computed(() => props.dirty === true || edited.value);
watch(() => props.dirty, (value, previous) => { if (previous === true && !value) edited.value = false; });
function close() { if (!isDirty.value || window.confirm('当前表单有未保存的修改，确认关闭？')) emit('close'); }
onMounted(() => element.value?.showModal());
</script>

<template>
  <dialog ref="element" class="um-admin-dialog" :class="{ 'is-wide': wide }" :aria-label="title" :data-dirty="isDirty" @input="edited = true" @change="edited = true" @cancel.prevent="!busy && close()">
    <header><h2>{{ title }}</h2><button type="button" class="icon" title="关闭" :disabled="busy" @click="close"><X :size="18" /></button></header>
    <slot />
  </dialog>
</template>
