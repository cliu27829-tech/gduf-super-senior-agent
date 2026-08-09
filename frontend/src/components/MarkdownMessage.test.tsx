import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownMessage } from "./MarkdownMessage";


describe("MarkdownMessage", () => {
  it("renders emphasis and lists without showing literal marker characters", () => {
    render(<MarkdownMessage content={"**重点**\n\n- 第一步\n- 第二步"} />);
    expect(screen.getByText("重点").tagName).toBe("STRONG");
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.queryByText("**重点**")).not.toBeInTheDocument();
  });

  it("renders GFM tables in a scroll container", () => {
    const { container } = render(<MarkdownMessage content={"| 地点 | 状态 |\n| --- | --- |\n| 西饭 | 待核验 |"} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(container.querySelector(".markdown-table")).toBeInTheDocument();
  });

  it("filters script tags and unsafe link protocols", () => {
    const { container } = render(<MarkdownMessage content={'<script>alert(1)</script>\n\n[危险](javascript:alert(1))\n\n[官网](https://www.gduf.edu.cn/)'} />);
    expect(container.querySelector("script")).not.toBeInTheDocument();
    expect(screen.getByText("危险").closest("a")).toBeNull();
    expect(screen.getByRole("link", { name: "官网" })).toHaveAttribute("href", "https://www.gduf.edu.cn/");
  });
});
