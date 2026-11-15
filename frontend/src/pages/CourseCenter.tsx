import { useInstitutionStore } from '@/store/useInstitutionStore';
import { CourseCenter as CourseWorkspace } from './course-center/CourseWorkspace';
import { SavedCourses } from './course-center/SavedCourses';

export function CourseCenter() {
  const hasCourseCatalog = useInstitutionStore(state => state.hasCourseCatalog);
  return hasCourseCatalog ? <CourseWorkspace /> : <SavedCourses />;
}
