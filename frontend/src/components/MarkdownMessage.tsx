import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";


export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="markdown-message">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          a: ({ href, children }) => {
            const safe = href?.startsWith("https://") || href?.startsWith("http://") || href?.startsWith("/");
            return safe ? <a href={href} target={href?.startsWith("/") ? undefined : "_blank"} rel="noreferrer">{children}</a> : <span>{children}</span>;
          },
          table: ({ children }) => <div className="markdown-table"><table>{children}</table></div>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
