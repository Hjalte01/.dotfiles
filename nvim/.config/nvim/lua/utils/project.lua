local M = {}

local codeforces_root = "/home/hjalte/Documents/side_projects/codeforces"

local function normalize(path)
  return vim.fn.fnamemodify(path, ":p"):gsub("/$", "")
end

function M.is_codeforces_path(path)
  path = path and path ~= "" and path or vim.fn.getcwd()
  path = normalize(path)
  return path == codeforces_root or vim.startswith(path, codeforces_root .. "/")
end

function M.is_codeforces_buffer(bufnr)
  bufnr = bufnr or 0
  local name = vim.api.nvim_buf_get_name(bufnr)
  return M.is_codeforces_path(name ~= "" and name or vim.fn.getcwd())
end

return M
