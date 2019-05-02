// Copyright (C) 2011, 2012 Google Inc.
//
// This file is part of ycmd.
//
// ycmd is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// ycmd is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with ycmd.  If not, see <http://www.gnu.org/licenses/>.

#include "CompletionData.h"
#include "ClangUtils.h"

#include <utility>

#ifndef DEBUG
#define DEBUG 0
#endif /* ifndef DEBUG */

namespace YouCompleteMe {

namespace {

CompletionKind CursorKindToCompletionKind( CXCursorKind kind ) {
  switch ( kind ) {
    case CXCursor_StructDecl:
      return CompletionKind::STRUCT;

    case CXCursor_ClassDecl:
    case CXCursor_ClassTemplate:
    case CXCursor_ObjCInterfaceDecl:
    case CXCursor_ObjCImplementationDecl:
      return CompletionKind::CLASS;

    case CXCursor_EnumDecl:
      return CompletionKind::ENUM;

    case CXCursor_UnexposedDecl:
    case CXCursor_UnionDecl:
    case CXCursor_TypedefDecl:
      return CompletionKind::TYPE;

    case CXCursor_FieldDecl:
    case CXCursor_ObjCIvarDecl:
    case CXCursor_ObjCPropertyDecl:
    case CXCursor_EnumConstantDecl:
      return CompletionKind::MEMBER;

    case CXCursor_FunctionDecl:
    case CXCursor_CXXMethod:
    case CXCursor_FunctionTemplate:
    case CXCursor_ConversionFunction:
    case CXCursor_Constructor:
    case CXCursor_Destructor:
    case CXCursor_ObjCClassMethodDecl:
    case CXCursor_ObjCInstanceMethodDecl:
      return CompletionKind::FUNCTION;

    case CXCursor_VarDecl:
      return CompletionKind::VARIABLE;

    case CXCursor_MacroDefinition:
      return CompletionKind::MACRO;

    case CXCursor_ParmDecl:
      return CompletionKind::PARAMETER;

    case CXCursor_Namespace:
    case CXCursor_NamespaceAlias:
      return CompletionKind::NAMESPACE;

    default:
      return CompletionKind::UNKNOWN;
  }
}

#if DEBUG
#define DLog(...) printf( __VA_ARGS__ )

int beforeCount = 0;
#define TOSTR(v) #v
static const char* kindDesc(CXCompletionChunkKind kind) {
    static const char* data[] = {
  TOSTR(CXCompletionChunk_Optional),
  TOSTR(CXCompletionChunk_TypedText),
  TOSTR(CXCompletionChunk_Text),
  TOSTR(CXCompletionChunk_Placeholder),
  TOSTR(CXCompletionChunk_Informative),
  TOSTR(CXCompletionChunk_CurrentParameter),
  TOSTR(CXCompletionChunk_LeftParen),
  TOSTR(CXCompletionChunk_RightParen),
  TOSTR(CXCompletionChunk_LeftBracket),
  TOSTR(CXCompletionChunk_RightBracket),
  TOSTR(CXCompletionChunk_LeftBrace),
  TOSTR(CXCompletionChunk_RightBrace),
  TOSTR(CXCompletionChunk_LeftAngle),
  TOSTR(CXCompletionChunk_RightAngle),
  TOSTR(CXCompletionChunk_Comma),
  TOSTR(CXCompletionChunk_ResultType),
  TOSTR(CXCompletionChunk_Colon),
  TOSTR(CXCompletionChunk_SemiColon),
  TOSTR(CXCompletionChunk_Equal),
  TOSTR(CXCompletionChunk_HorizontalSpace),
  TOSTR(CXCompletionChunk_VerticalSpace)
};
  return data[kind];
}
#else
#define DLog(...)
#endif


bool IsMainCompletionTextInfo( CXCompletionChunkKind kind ) {
  return
    kind == CXCompletionChunk_Optional     ||
    kind == CXCompletionChunk_TypedText    ||
    kind == CXCompletionChunk_Placeholder  ||
    kind == CXCompletionChunk_LeftParen    ||
    kind == CXCompletionChunk_RightParen   ||
    kind == CXCompletionChunk_RightBracket ||
    kind == CXCompletionChunk_LeftBracket  ||
    kind == CXCompletionChunk_LeftBrace    ||
    kind == CXCompletionChunk_RightBrace   ||
    kind == CXCompletionChunk_RightAngle   ||
    kind == CXCompletionChunk_LeftAngle    ||
    kind == CXCompletionChunk_Comma        ||
    kind == CXCompletionChunk_Colon        ||
    kind == CXCompletionChunk_SemiColon    ||
    kind == CXCompletionChunk_Equal        ||
    kind == CXCompletionChunk_Informative  ||
    kind == CXCompletionChunk_HorizontalSpace ||
    kind == CXCompletionChunk_Text;

}


std::string ChunkToString( CXCompletionString completion_string,
                           size_t chunk_num ) {
  if ( !completion_string ) {
    return std::string();
  }

  return CXStringToString(
           clang_getCompletionChunkText( completion_string, chunk_num ) );
}


std::string OptionalChunkToString( CXCompletionString completion_string,
                                   size_t chunk_num ) {
  std::string final_string;

  if ( !completion_string ) {
    return final_string;
  }

  CXCompletionString optional_completion_string =
    clang_getCompletionChunkCompletionString( completion_string, chunk_num );

  if ( !optional_completion_string ) {
    return final_string;
  }

  size_t optional_num_chunks = clang_getNumCompletionChunks(
                               optional_completion_string );

  for ( size_t j = 0; j < optional_num_chunks; ++j ) {
    CXCompletionChunkKind kind = clang_getCompletionChunkKind(
                                   optional_completion_string, j );

    if ( kind == CXCompletionChunk_Optional ) {
      final_string.append( OptionalChunkToString( optional_completion_string,
                                                  j ) );
    } else {
      final_string.append( ChunkToString( optional_completion_string, j ) );
    }
  }

  return final_string;
}

} // unnamed namespace


CompletionData::CompletionData( CXCompletionString completion_string,
                                CXCursorKind kind,
                                CXCodeCompleteResults *results,
                                size_t index ) {
  size_t num_chunks = clang_getNumCompletionChunks( completion_string );
  bool saw_left_paren = false;
  bool saw_function_params = false;
   DLog("before extract %d\n", beforeCount++);
  for ( size_t j = 0; j < num_chunks; ++j ) {
    ExtractDataFromChunk( completion_string,
                          j,
                          saw_left_paren,
                          saw_function_params);
  }

  kind_ = CursorKindToCompletionKind( kind );

  detailed_info_.append( return_type_ )
  .append( " " )
  .append( everything_except_return_type_ )
  .append( "\n" );

  doc_string_ = CXStringToString(
    clang_getCompletionBriefComment( completion_string ) );

  BuildCompletionFixIt( results, index );
}


void CompletionData::ExtractDataFromChunk( CXCompletionString completion_string,
                                           size_t chunk_num,
                                           bool &saw_left_paren,
                                           bool &saw_function_params) {
  CXCompletionChunkKind kind = clang_getCompletionChunkKind(
                                 completion_string, chunk_num );
   DLog("%d %s %s\n",kind, kindDesc(kind), ChunkToString(completion_string, chunk_num).c_str());

  if ( IsMainCompletionTextInfo( kind ) ) {
    if ( kind == CXCompletionChunk_LeftParen ) {
      saw_left_paren = true;
    } else if ( saw_left_paren &&
                !saw_function_params &&
                kind != CXCompletionChunk_RightParen &&
                kind != CXCompletionChunk_Informative ) {
      saw_function_params = true;
      everything_except_return_type_.append( " " );
    } else if ( saw_function_params && kind == CXCompletionChunk_RightParen ) {
      // in objc complete declared method, there have multi paren.
      // if not set false, everything_except_return_type_ will
      // have space at right but doesn't have at left
      saw_left_paren = false;
      saw_function_params = false;
      everything_except_return_type_.append( " " );
    }

    if ( kind == CXCompletionChunk_Optional ) {
      everything_except_return_type_.append(
        OptionalChunkToString( completion_string, chunk_num ) );
    } else {
      everything_except_return_type_.append(
        ChunkToString( completion_string, chunk_num ) );
    }
  }

  switch ( kind ) {
    case CXCompletionChunk_ResultType:
      return_type_ = ChunkToString( completion_string, chunk_num );
      break;

    case CXCompletionChunk_Placeholder:
      template_string_ += "<#";
      template_string_ += ChunkToString(completion_string, chunk_num);
      template_string_ += "#>";
      break;

    case CXCompletionChunk_TypedText:
      original_string_ +=  ChunkToString( completion_string, chunk_num );
    case CXCompletionChunk_Text:

    case CXCompletionChunk_RightBracket:
    case CXCompletionChunk_LeftBracket:
    case CXCompletionChunk_LeftBrace:
    case CXCompletionChunk_RightBrace:
    case CXCompletionChunk_RightAngle:
    case CXCompletionChunk_LeftAngle:
    case CXCompletionChunk_Comma:
    case CXCompletionChunk_Colon:
    case CXCompletionChunk_SemiColon:
    case CXCompletionChunk_Equal:
    case CXCompletionChunk_LeftParen:
    case CXCompletionChunk_RightParen:
    case CXCompletionChunk_HorizontalSpace:
      template_string_ += ChunkToString( completion_string, chunk_num );
      break;

    default:
      break;
  }
}


void CompletionData::BuildCompletionFixIt( CXCodeCompleteResults *results,
                                           size_t index ) {
  size_t num_chunks = clang_getCompletionNumFixIts( results, index );
  if ( !num_chunks ) {
    return;
  }

  fixit_.chunks.reserve( num_chunks );

  for ( size_t chunk_index = 0; chunk_index < num_chunks; ++chunk_index ) {
    FixItChunk chunk;
    CXSourceRange range;
    chunk.replacement_text = CXStringToString(
                               clang_getCompletionFixIt( results,
                                                         index,
                                                         chunk_index,
                                                         &range ) );

    chunk.range = Range( range );
    fixit_.chunks.push_back( chunk );
  }
}

} // namespace YouCompleteMe
