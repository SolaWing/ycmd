// Copyright (C) 2017-2018 ycmd contributors
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

#include "TestUtils.h"
#include "Utils.h"
#include "PythonSupport.h"

#include <gtest/gtest.h>

namespace YouCompleteMe {

class UtilsTest : public ::testing::Test {
protected:
  virtual void SetUp() {
    // The returned temporary path is a symlink on macOS.
    tmp_dir = fs::canonical( fs::temp_directory_path() ) / fs::unique_path();
    existing_path = tmp_dir / "existing_path";
    symlink = tmp_dir / "symlink";
    fs::create_directories( existing_path );
    fs::create_directory_symlink( existing_path, symlink );
  }

  virtual void TearDown() {
    fs::remove_all( tmp_dir );
  }

  fs::path tmp_dir;
  fs::path existing_path;
  fs::path symlink;
};


TEST_F( UtilsTest, IsUppercase ) {
  EXPECT_TRUE( IsUppercase( 'A' ) );
  EXPECT_TRUE( IsUppercase( 'B' ) );
  EXPECT_TRUE( IsUppercase( 'Z' ) );

  EXPECT_FALSE( IsUppercase( 'a' ) );
  EXPECT_FALSE( IsUppercase( 'b' ) );
  EXPECT_FALSE( IsUppercase( 'z' ) );

  EXPECT_FALSE( IsUppercase( '$' ) );
  EXPECT_FALSE( IsUppercase( '@' ) );
  EXPECT_FALSE( IsUppercase( '~' ) );
}

TEST_F( UtilsTest, Lowercase ) {
  EXPECT_EQ( Lowercase( 'a' ), 'a' );
  EXPECT_EQ( Lowercase( 'z' ), 'z' );
  EXPECT_EQ( Lowercase( 'A' ), 'a' );
  EXPECT_EQ( Lowercase( 'Z' ), 'z' );
  EXPECT_EQ( Lowercase( ';' ), ';' );

  EXPECT_EQ( Lowercase( "lOwER_CasE" ), "lower_case" );
}


TEST_F( UtilsTest, NormalizePath ) {
  EXPECT_THAT( NormalizePath( "" ),   Equals( fs::current_path() ) );
  EXPECT_THAT( NormalizePath( "." ),  Equals( fs::current_path() ) );
  EXPECT_THAT( NormalizePath( "./" ), Equals( fs::current_path() ) );
  EXPECT_THAT( NormalizePath( existing_path ),       Equals( existing_path ) );
  EXPECT_THAT( NormalizePath( "", existing_path ),   Equals( existing_path ) );
  EXPECT_THAT( NormalizePath( ".", existing_path ),  Equals( existing_path ) );
  EXPECT_THAT( NormalizePath( "./", existing_path ), Equals( existing_path ) );
  EXPECT_THAT( NormalizePath( symlink ),             Equals( existing_path ) );
  EXPECT_THAT( NormalizePath( "", symlink ),         Equals( existing_path ) );
  EXPECT_THAT( NormalizePath( ".", symlink ),        Equals( existing_path ) );
  EXPECT_THAT( NormalizePath( "./", symlink ),       Equals( existing_path ) );
  EXPECT_THAT( NormalizePath( existing_path / "foo/../bar/./xyz//" ),
               Equals( existing_path / "bar" / "xyz" ) );
  EXPECT_THAT( NormalizePath( "foo/../bar/./xyz//", existing_path ),
               Equals( existing_path / "bar" / "xyz" ) );
  EXPECT_THAT( NormalizePath( symlink / "foo/../bar/./xyz//" ),
               Equals( existing_path / "bar" / "xyz" ) );
  EXPECT_THAT( NormalizePath( "foo/../bar/./xyz//", symlink ),
               Equals( existing_path / "bar" / "xyz" ) );
}

TEST_F( UtilsTest, DiffString ) {
    { // 相等
        auto a = DiffString("abc", "abc");
        EXPECT_THAT( a,   Equals( decltype(a){0, 0, ""} ) );
    }
    { // 全部添加
        auto a = DiffString("", "abcde");
        EXPECT_THAT( a,   Equals( decltype(a){0, 0, "abcde"} ) );
    }
    { // 全部删除
        auto a = DiffString("abcde", "");
        EXPECT_THAT( a,   Equals( decltype(a){0, 5, ""} ) );
    }
    { // 加后缀
        auto a = DiffString("abc", "abcde");
        EXPECT_THAT( a,   Equals( decltype(a){3, 0, "de"} ) );
    }
    { // 删后缀
        auto a = DiffString("abc", "ab");
        EXPECT_THAT( a,   Equals( decltype(a){2, 1, ""} ) );
    }
    { // 加前缀
        auto a = DiffString("abc", "ddabc");
        EXPECT_THAT( a,   Equals( decltype(a){0, 0, "dd"} ) );
    }
    { // 删除前缀
        auto a = DiffString("abc", "bc");
        EXPECT_THAT( a,   Equals( decltype(a){0, 1, ""} ) );
    }
    { // 改中间
        auto a = DiffString("abcde", "abgde");
        EXPECT_THAT( a,   Equals( decltype(a){2, 1, "g"} ) );
    }
    {
        auto a = DiffString("abcde", "abggde");
        EXPECT_THAT( a,   Equals( decltype(a){2, 1, "gg"} ) );
    }
    { // 加中间
        auto a = DiffString("abcde", "abcggde");
        EXPECT_THAT( a,   Equals( decltype(a){3, 0, "gg"} ) );
    }
    { // 减中间
        auto a = DiffString("abcde", "abde");
        EXPECT_THAT( a,   Equals( decltype(a){2, 1, ""} ) );
    }
    { // 后缀子串
        auto a = DiffString("abcde", "ababcde");
        EXPECT_THAT( a,   Equals( decltype(a){0, 0, "ab"} ) );
    }
    { // 前缀子串
        auto a = DiffString("abcde", "abcdede");
        EXPECT_THAT( a,   Equals( decltype(a){3, 0, "de"} ) );
    }
    { // utf8前缀
        auto a = DiffString(u8"\u00a3", u8"\u00a4");
        EXPECT_THAT( a,   Equals( decltype(a){0, 2, u8"\u00a4"} ) );
    }
    { // utf8后缀
        auto a = DiffString("\xc2\xa2", "\xc3\xa2");
        EXPECT_THAT( a,   Equals( decltype(a){0, 2, u8"\xc3\xa2"} ) );
    }
}

} // namespace YouCompleteMe
