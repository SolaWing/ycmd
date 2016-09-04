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

#include <gtest/gtest.h>
#include <gmock/gmock.h>
#include "IdentifierCompleter.h"
#include "Utils.h"
#include "TestUtils.h"

using ::testing::ElementsAre;
using ::testing::IsEmpty;
using ::testing::WhenSorted;

namespace YouCompleteMe {


// This differs from what we expect from the ClangCompleter. That one should
// return results for an empty query.
    
TEST( IdentifierCompleterTest, EmptyQueryNoResults ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "foobar" ) ).CandidatesForQuery( "" ),
               IsEmpty() );
}

TEST( IdentifierCompleterTest, NoDuplicatesReturned ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "foobar",
                   "foobar",
                   "foobar" ) ).CandidatesForQuery( "foo" ),
               ElementsAre( "foobar" ) );
}


TEST( IdentifierCompleterTest, OneCandidate ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "foobar" ) ).CandidatesForQuery( "fbr" ),
               ElementsAre( "foobar" ) );
}

TEST( IdentifierCompleterTest, ManyCandidateSimple ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "foobar",
                   "foobartest",
                   "Foobartest" ) ).CandidatesForQuery( "fbr" ),
               WhenSorted( ElementsAre( "Foobartest",
                                        "foobar",
                                        "foobartest" ) ) );
}

TEST( IdentifierCompleterTest, SmartCaseFiltering ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "fooBar",
                   "fooBaR" ) ).CandidatesForQuery( "fBr" ),
               ElementsAre( "fooBaR",
                            "fooBar" ) );
}

TEST( IdentifierCompleterTest, FirstCharSameAsQueryWins ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "foobar",
                   "afoobar" ) ).CandidatesForQuery( "fbr" ),
               ElementsAre( "foobar",
                            "afoobar" ) );
}

TEST( IdentifierCompleterTest, CompleteMatchForWordBoundaryCharsWins ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "FooBarQux",
                   "FBaqux" ) ).CandidatesForQuery( "fbq" ),
               ElementsAre( "FooBarQux",
                            "FBaqux" ) );

  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "CompleterTest",
                   "CompleteMatchForWordBoundaryCharsWins" ) )
               .CandidatesForQuery( "ct" ),
               ElementsAre( "CompleterTest",
                            "CompleteMatchForWordBoundaryCharsWins" ) );

  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "FooBarx",
                   "FooBarRux" ) ).CandidatesForQuery( "fbr" ),
               ElementsAre( "FooBarRux",
                            "FooBarx" ) );

  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "foo-barx",
                   "foo-bar-rux" ) ).CandidatesForQuery( "fbr" ),
               ElementsAre( "foo-bar-rux",
                            "foo-barx" ) );

  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "foo.barx",
                   "foo.bar.rux" ) ).CandidatesForQuery( "fbr" ),
               ElementsAre( "foo.bar.rux",
                            "foo.barx" ) );
}

TEST( IdentifierCompleterTest, RatioUtilizationTieBreak ) {
  // EXPECT_THAT( IdentifierCompleter(
  //                StringVector(
  //                  "aCaaFoogxx",
  //                  "aCaafoog" ) ).CandidatesForQuery( "caafoo" ),
  //              ElementsAre( "aCaaFoogxx",
  //                           "aCaafoog" ) );

  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "FooBarQux",
                   "FooBarQuxZaa" ) ).CandidatesForQuery( "fbq" ),
               ElementsAre( "FooBarQux",
                            "FooBarQuxZaa" ) );

  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "FooBar",
                   "FooBarRux" ) ).CandidatesForQuery( "fba" ),
               ElementsAre( "FooBar",
                            "FooBarRux" ) );
}

TEST( IdentifierCompleterTest, QueryPrefixOfCandidateWins ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "foobar",
                   "fbaroo" ) ).CandidatesForQuery( "foo" ),
               ElementsAre( "foobar",
                            "fbaroo" ) );
}

TEST( IdentifierCompleterTest, LowerMatchCharIndexSumWins ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "ratio_of_word_boundary_chars_in_query_",
                   "first_char_same_in_query_and_text_" ) )
               .CandidatesForQuery( "charinq" ),
               ElementsAre( "first_char_same_in_query_and_text_",
                            "ratio_of_word_boundary_chars_in_query_" ) );

  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "barfooq",
                   "barquxfooq" ) ).CandidatesForQuery( "foo" ),
               ElementsAre( "barfooq",
                            "barquxfooq" ) );

  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "xxxxxabcx",
                   "xxabcxxxx" ) ).CandidatesForQuery( "abc" ),
               ElementsAre( "xxabcxxxx",
                            "xxxxxabcx" ) );

  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "FooBarQux",
                   "FaBarQux" ) ).CandidatesForQuery( "fbq" ),
               ElementsAre( "FaBarQux",
                            "FooBarQux" ) );
}

TEST( IdentifierCompleterTest, ShorterCandidateWins ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "cache",
                   "cacheBtnClick" ) ).CandidatesForQuery( "cach" ),
               ElementsAre( "cache",
                            "cacheBtnClick" ) );

  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "CompleterT",
                   "CompleterTest" ) ).CandidatesForQuery( "co" ),
               ElementsAre( "CompleterT",
                            "CompleterTest" ) );

  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "CompleterT",
                   "CompleterTest" ) ).CandidatesForQuery( "plet" ),
               ElementsAre( "CompleterT",
                            "CompleterTest" ) );
}

TEST( IdentifierCompleterTest, SameLowercaseCandidateWins ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "foobar",
                   "Foobar" ) ).CandidatesForQuery( "foo" ),
               ElementsAre( "foobar",
                            "Foobar" ) );

}

TEST( IdentifierCompleterTest, PreferLowercaseCandidate ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "chatContentExtension",
                   "ChatContentExtension" ) ).CandidatesForQuery(
                 "chatContent" ),
               ElementsAre( "chatContentExtension",
                            "ChatContentExtension" ) );
    
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "CCLOG",
                   "cclog") ).CandidatesForQuery( "ccl" ),
               ElementsAre( "cclog",
                            "CCLOG") );
}

TEST( IdentifierCompleterTest, ShorterAndLowercaseWins ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "STDIN_FILENO",
                   "stdin" ) ).CandidatesForQuery( "std" ),
               ElementsAre( "stdin",
                            "STDIN_FILENO" ) );
}


TEST( IdentifierCompleterTest, NonAlnumChars ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "font-family",
                   "font-face" ) ).CandidatesForQuery( "fo" ),
               ElementsAre( "font-face",
                            "font-family" ) );
}


TEST( IdentifierCompleterTest, NonAlnumStartChar ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "-zoo-foo" ) ).CandidatesForQuery( "-z" ),
               ElementsAre( "-zoo-foo" ) );
}


TEST( IdentifierCompleterTest, EmptyCandidatesForUnicode ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "uni¢𐍈d€" ) ).CandidatesForQuery( "¢" ),
               IsEmpty() );
}


TEST( IdentifierCompleterTest, EmptyCandidatesForNonPrintable ) {
  EXPECT_THAT( IdentifierCompleter(
                 StringVector(
                   "\x01\x1f\x7f" ) ).CandidatesForQuery( "\x1f" ),
               IsEmpty() );
}


TEST( IdentifierCompleterTest, TagsEndToEndWorks ) {
  IdentifierCompleter completer;
  std::vector< std::string > tag_files;
  tag_files.push_back( PathToTestFile( "basic.tags" ).string() );

  completer.AddIdentifiersToDatabaseFromTagFiles( tag_files );

  EXPECT_THAT( completer.CandidatesForQueryAndType( "fo", "cpp" ),
               ElementsAre( "foosy",
                            "fooaaa" ) );

}

// TODO: tests for filepath and filetype candidate storing

} // namespace YouCompleteMe

