import './previewApi';

/** Controls surround the real App; routes and pages are never substituted. */
export function PreviewControls() {
  return <div className="um-full-preview-bar">
    <span><span className="um-preview-name">UniMind.ai · 完整应用 · </span>本地示例数据</span>
    <label>身份 <select aria-label="调试身份" defaultValue={sessionStorage.getItem('unimind-preview-role') || 'student'} onChange={event => {
      sessionStorage.setItem('unimind-preview-role', event.target.value);
      location.assign('/?preview=1');
    }}><option value="student">学生</option><option value="teacher">教师 / 机构</option><option value="admin">平台管理员</option></select></label>
    <a href="/?preview=0">连接真实后端</a>
  </div>;
}
