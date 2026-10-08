import { WorkspacePage } from '../../../workspace/provider';
export default async function Page({ params }) {
  const { id } = await params;
  return <WorkspacePage name="editorPage" id={id} />;
}
